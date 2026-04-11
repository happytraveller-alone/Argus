from app.api.v1.endpoints.projects_shared import *
from app.api.v1.endpoints.projects_shared import (
    _build_zip_project,
    _get_or_prepare_project_info,
    _raise_if_project_hidden,
    _resolve_project_description_bundle,
    _store_uploaded_archive_for_project,
    _validate_archive_extension,
)
from app.services.project_metrics import ProjectMetricsService, project_metrics_refresher

router = APIRouter()


@router.post(
    "/description/generate",
    response_model=ProjectDescriptionGenerateResponse,
)
async def generate_project_description_preview(
    file: UploadFile = File(...),
    project_name: Optional[str] = Form(None),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(deps.get_current_user),
) -> Any:
    """
    根据上传压缩包生成项目描述（不创建项目，不写数据库）。
    """
    if not file.filename:
        raise HTTPException(status_code=400, detail="文件名不能为空")

    _validate_archive_extension(file.filename)

    with tempfile.TemporaryDirectory(prefix="VulHunter_", suffix="_desc_generate") as temp_dir:
        try:
            temp_upload_path = os.path.join(temp_dir, file.filename)
            with open(temp_upload_path, "wb") as buffer:
                shutil.copyfileobj(file.file, buffer)

            is_valid, error = UploadManager.validate_file(temp_upload_path)
            if not is_valid:
                raise HTTPException(status_code=400, detail=f"文件验证失败: {error}")

            temp_extract_dir = os.path.join(temp_dir, "extracted")
            os.makedirs(temp_extract_dir, exist_ok=True)
            success, extracted_files, error = await UploadManager.extract_file(
                temp_upload_path,
                temp_extract_dir,
                max_files=100000,
            )
            if not success:
                raise HTTPException(status_code=400, detail=f"解压失败: {error}")

            description, language_info, source = await _resolve_project_description_bundle(
                extracted_dir=temp_extract_dir,
                extracted_files=extracted_files,
                project_name=project_name,
                db=db,
                user_id=current_user.id,
            )

            return ProjectDescriptionGenerateResponse(
                description=description,
                language_info=language_info,
                source=source,
            )
        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"生成项目描述失败: {e}", exc_info=True)
            raise HTTPException(status_code=500, detail=f"生成项目描述失败: {str(e)}")


@router.post(
    "/{id}/description/generate",
    response_model=ProjectDescriptionGenerateResponse,
)
async def generate_project_description_for_project(
    id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(deps.get_current_user),
) -> Any:
    """
    基于项目已存储的压缩包生成并持久化项目简介。
    """
    project = await db.get(Project, id)
    _raise_if_project_hidden(project)

    zip_path = await load_project_zip(id)
    if not zip_path or not os.path.exists(zip_path):
        raise HTTPException(status_code=404, detail="未找到项目压缩包")

    project_info = await _get_or_prepare_project_info(db, id)

    try:
        project_info.status = "pending"
        db.add(project_info)
        await db.commit()
        await db.refresh(project_info)

        with tempfile.TemporaryDirectory(
            prefix="VulHunter_",
            suffix="_stored_desc_generate",
        ) as temp_dir:
            extracted_dir = os.path.join(temp_dir, "extracted")
            os.makedirs(extracted_dir, exist_ok=True)

            success, extracted_files, error = await UploadManager.extract_file(
                zip_path,
                extracted_dir,
                max_files=100000,
            )
            if not success:
                raise HTTPException(status_code=400, detail=f"解压失败: {error}")

            description, language_info, source = await _resolve_project_description_bundle(
                extracted_dir=extracted_dir,
                extracted_files=extracted_files,
                project_name=project.name,
                db=db,
                user_id=current_user.id,
            )

            project.description = description
            project.updated_at = datetime.now(timezone.utc)
            project_info.language_info = language_info
            project_info.description = description
            project_info.status = "completed"

            db.add(project)
            db.add(project_info)
            await db.commit()
            await db.refresh(project)
            await db.refresh(project_info)

            return ProjectDescriptionGenerateResponse(
                description=description,
                language_info=language_info,
                source=source,
            )
    except HTTPException:
        try:
            project_info.status = "failed"
            db.add(project_info)
            await db.commit()
        except Exception:
            logger.exception("保存项目简介失败状态时出错")
        raise
    except Exception as e:
        logger.error(f"生成项目简介失败: {e}", exc_info=True)
        try:
            project_info.status = "failed"
            db.add(project_info)
            await db.commit()
        except Exception:
            logger.exception("保存项目简介失败状态时出错")
        raise HTTPException(status_code=500, detail=f"生成项目简介失败: {str(e)}")


@router.post("/create-with-zip", response_model=ProjectResponse)
async def create_project_with_zip(
    name: str = Form(...),
    file: UploadFile = File(...),
    description: Optional[str] = Form(None),
    default_branch: Optional[str] = Form(None),
    programming_languages: Optional[List[str]] = Form(None),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(deps.get_current_user),
) -> Any:
    project = _build_zip_project(
        name=name,
        description=description,
        default_branch=default_branch,
        programming_languages=programming_languages,
        owner_id=current_user.id,
    )
    db.add(project)

    try:
        await _store_uploaded_archive_for_project(
            db=db,
            project=project,
            file=file,
            user_id=current_user.id,
            commit=False,
        )
        try:
            await db.commit()
            project_metrics_refresher.enqueue(project.id)
        except IntegrityError:
            await db.rollback()
            await delete_project_zip(project.id)
            raise HTTPException(
                status_code=409,
                detail="检测到相同压缩包已存在，请勿重复上传",
            )
        return await load_project_for_response(
            db,
            project.id,
            include_metrics=False,
        )
    except HTTPException:
        await db.rollback()
        await delete_project_zip(project.id)
        raise
    except Exception as exc:
        await db.rollback()
        await delete_project_zip(project.id)
        raise HTTPException(status_code=500, detail=f"上传失败: {str(exc)}") from exc


@router.get("/{id}/zip", response_model=ZipFileMetaResponse)
async def get_project_zip_info(
    id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(deps.get_current_user),
) -> Any:
    """
    获取项目ZIP文件信息
    """
    project = await db.get(Project, id)
    _raise_if_project_hidden(project)

    # 检查是否有ZIP文件
    has_file = await has_project_zip(id)
    if not has_file:
        return {"has_file": False}

    # 获取元数据
    meta = await get_project_zip_meta(id)
    if meta:
        return {
            "has_file": True,
            "original_filename": meta.get("original_filename"),
            "file_size": meta.get("file_size"),
            "uploaded_at": meta.get("uploaded_at"),
        }

    return {"has_file": True}


@router.post("/{id}/zip")
async def upload_project_zip(
    id: str,
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(deps.get_current_user),
) -> Any:
    """
    上传项目文件（支持多种压缩格式）

    支持的格式: .zip, .tar, .tar.gz, .tar.bz2, .7z, .rar 等
    所有格式都会被转换为 .zip 格式保存

    工作流程：
    1. 验证文件格式是否支持
    2. 保存上传的压缩文件到临时位置
    3. 验证文件完整性
    4. 解压到临时目录
    5. 重新压缩为 .zip 格式
    6. 保存到项目存储
    7. 清理临时文件
    """
    project = await db.get(Project, id)
    _raise_if_project_hidden(project)
    result = await _store_uploaded_archive_for_project(
        db=db,
        project=project,
        file=file,
        user_id=current_user.id,
        commit=True,
    )
    project_metrics_refresher.enqueue(project.id)
    return result


@router.get("/{id}/upload/preview")
async def preview_upload_file(
    id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(deps.get_current_user),
) -> Any:
    """
    获取上传文件预览信息

    返回压缩包内的文件列表和统计信息
    """
    project = await db.get(Project, id)
    _raise_if_project_hidden(project)

    if project.source_type != "zip":
        raise HTTPException(status_code=400, detail="仅ZIP类型项目支持")

    # 获取 ZIP 文件
    zip_path = await load_project_zip(id)
    if not zip_path or not os.path.exists(zip_path):
        raise HTTPException(status_code=404, detail="未找到上传的文件")

    success, file_list, error = UploadManager.get_file_list_preview(zip_path, limit=50)
    if not success:
        raise HTTPException(status_code=500, detail=error)

    return {
        "file_count": len(file_list),
        "files": file_list,
        "supported_formats": list(CompressionStrategyFactory.get_supported_formats()),
    }


@router.post("/{id}/directory")
async def upload_project_directory(
    id: str,
    files: List[UploadFile] = File(...),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(deps.get_current_user),
) -> Any:
    """
    上传文件夹（实际为多个文件）

    工作流程：
    1. 验证项目权限
    2. 使用 tempfile 创建临时目录
    3. 将所有文件保存到临时目录（保持目录结构）
    4. 压缩成 ZIP 文件
    5. 保存到项目存储
    6. 自动清理临时目录和文件

    参数：
    - files: 多个文件，前端应该保持相对路径信息（通过 webkitRelativePath）
    """
    project = await db.get(Project, id)
    _raise_if_project_hidden(project)

    # 检查权限

    # 检查项目类型
    if project.source_type != "zip":
        raise HTTPException(status_code=400, detail="仅ZIP类型项目可以上传文件")

    if not files:
        raise HTTPException(status_code=400, detail="至少需要上传一个文件")

    # 使用 tempfile 创建临时目录（自动清理）
    with tempfile.TemporaryDirectory(prefix="VulHunter_", suffix="_upload") as temp_base_dir:
        try:
            total_size = 0
            file_count = 0
            uploaded_paths: List[str] = []

            # 逐个保存文件，保持目录结构
            for file in files:
                if not file.filename:
                    continue

                # 获取文件的相对路径（保持目录结构）
                # 例如：src/main.py, tests/unit/test.py
                file_path = file.filename

                # 移除开头的 "/"（如果存在）
                if file_path.startswith("/"):
                    file_path = file_path[1:]

                if should_exclude_file(file_path):
                    continue

                # 检查文件大小
                file_content = await file.read()
                file_size = len(file_content)

                if file_size == 0:
                    continue  # 跳过空文件

                total_size += file_size
                file_count += 1

                # 检查总大小是否超过限制（500MB）
                if total_size > 500 * 1024 * 1024:
                    raise HTTPException(status_code=400, detail="文件总大小不能超过 500MB")

                # 完整的目标路径
                target_path = os.path.join(temp_base_dir, file_path)

                # 创建必要的目录
                target_dir = os.path.dirname(target_path)
                os.makedirs(target_dir, exist_ok=True)

                # 保存文件
                with open(target_path, "wb") as f:
                    f.write(file_content)
                uploaded_paths.append(file_path)

            if file_count == 0:
                raise HTTPException(status_code=400, detail="没有有效的文件")

            # 使用 tempfile 创建临时 ZIP 文件
            with tempfile.NamedTemporaryFile(
                suffix=".zip", prefix="VulHunter_", delete=False
            ) as temp_zip_file:
                temp_zip_path = temp_zip_file.name

            try:
                # 使用 shutil.make_archive 压缩
                archive_path = shutil.make_archive(
                    temp_zip_path.replace(".zip", ""),  # 去掉 .zip 后缀（make_archive 会自动添加）
                    "zip",
                    temp_base_dir,
                )
            except Exception as e:
                # 清理临时 ZIP 文件
                if os.path.exists(temp_zip_path):
                    os.remove(temp_zip_path)
                raise HTTPException(status_code=500, detail=f"压缩文件失败: {str(e)}")

            # 验证压缩文件
            is_valid, error = UploadManager.validate_file(temp_zip_path)
            if not is_valid:
                if os.path.exists(temp_zip_path):
                    os.remove(temp_zip_path)
                raise HTTPException(status_code=400, detail=f"压缩文件验证失败: {error}")

            # 获取文件预览
            success, file_list, error = UploadManager.get_file_list_preview(temp_zip_path)
            if not success:
                if os.path.exists(temp_zip_path):
                    os.remove(temp_zip_path)
                raise HTTPException(status_code=400, detail=error)

            # 计算压缩包内容哈希，避免重复上传
            zip_hash = calculate_file_sha256(temp_zip_path)

            # 同一项目重复上传相同压缩包直接拒绝
            if project.zip_file_hash and project.zip_file_hash == zip_hash:
                if os.path.exists(temp_zip_path):
                    os.remove(temp_zip_path)
                raise HTTPException(
                    status_code=409,
                    detail="当前项目已上传相同内容压缩包，无需重复上传",
                )

            # 检查是否与其他项目重复
            duplicate_project = await find_duplicate_zip_project(db, zip_hash, id)
            if duplicate_project:
                if os.path.exists(temp_zip_path):
                    os.remove(temp_zip_path)
                raise HTTPException(
                    status_code=409,
                    detail=f"检测到相同压缩包已上传到项目「{duplicate_project.name}」，请勿重复上传",
                )

            # 生成文件名为项目ID
            archive_filename = f"{id}.zip"

            # 保存到项目存储
            try:
                meta = await save_project_zip(id, temp_zip_path, archive_filename)
            finally:
                # 确保临时 ZIP 文件被清理
                if os.path.exists(temp_zip_path):
                    os.remove(temp_zip_path)

            detected_languages = detect_languages_from_paths(uploaded_paths)
            project.programming_languages = json.dumps(detected_languages, ensure_ascii=False)
            project.zip_file_hash = zip_hash
            await ProjectMetricsService.ensure_base_metrics(db, project.id)
            try:
                await db.commit()
                await db.refresh(project)
                project_metrics_refresher.enqueue(project.id)
            except IntegrityError:
                await db.rollback()
                await delete_project_zip(id)
                raise HTTPException(
                    status_code=409,
                    detail="检测到相同压缩包已存在，请勿重复上传",
                )

            return {
                "message": "文件夹上传成功",
                "file_count": file_count,
                "total_size": total_size,
                "total_size_mb": f"{total_size / 1024 / 1024:.2f}",
                "original_filename": meta["original_filename"],
                "file_size": meta["file_size"],
                "uploaded_at": meta["uploaded_at"],
                "file_hash": zip_hash,
                "format": ".zip",
                "archive_file_count": len(file_list),
                "sample_files": file_list[:10],
                "detected_languages": detected_languages,
            }

        except HTTPException:
            raise
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"上传失败: {str(e)}")


@router.delete("/{id}/zip")
async def delete_project_zip_file(
    id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(deps.get_current_user),
) -> Any:
    """
    删除项目ZIP文件
    """
    project = await db.get(Project, id)
    _raise_if_project_hidden(project)

    # 检查权限

    deleted = await delete_project_zip(id)
    if deleted:
        project.zip_file_hash = None
        await db.commit()
        project_metrics_refresher.enqueue(project.id)

    if deleted:
        return {"message": "ZIP文件已删除"}
    else:
        return {"message": "没有找到ZIP文件"}
