from app.api.v1.endpoints.projects_shared import *
from app.api.v1.endpoints.projects_shared import (
    _calculate_zip_file_hash,
    _raise_if_project_hidden,
    _build_file_tree_from_zip,
    _validate_zip_file_path,
    _is_binary_file,
)

router = APIRouter()


@router.get("/{id}/files")
async def get_project_files(
    id: str,
    exclude_patterns: Optional[str] = None,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(deps.get_current_user),
) -> Any:
    """
    Get list of files in the project.
    可选参数:
    - exclude_patterns: JSON 格式的排除模式数组，如 ["node_modules/**", "*.log"]
    """
    project = await db.get(Project, id)
    _raise_if_project_hidden(project)

    # Check permissions

    # 解析排除模式
    parsed_exclude_patterns = []
    if exclude_patterns:
        try:
            parsed_exclude_patterns = json.loads(exclude_patterns)
        except json.JSONDecodeError:
            pass

    files = []

    if project.source_type == "zip":
        # Handle ZIP project
        zip_path = await load_project_zip(id)
        print(f"ZIP项目 {id} 文件路径: {zip_path}")
        if not zip_path or not os.path.exists(zip_path):
            print(f"ZIP文件不存在: {zip_path}")
            return []

        try:
            with zipfile.ZipFile(zip_path, "r") as zip_ref:
                for file_info in zip_ref.infolist():
                    if not file_info.is_dir():
                        name = file_info.filename
                        # 使用统一的排除逻辑，支持用户自定义排除模式
                        if should_exclude(name, parsed_exclude_patterns):
                            continue
                        # 只显示支持的代码文件
                        if not is_text_file(name):
                            continue
                        files.append({"path": name, "size": file_info.file_size})
        except Exception as e:
            print(f"Error reading zip file: {e}")
            raise HTTPException(status_code=500, detail="无法读取项目文件")

    return files


@router.get("/{id}/files-tree", response_model=FileTreeResponse)
async def get_project_files_tree(
    id: str,
    exclude_patterns: Optional[str] = None,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(deps.get_current_user),
) -> Any:
    """
    获取项目文件树结构（嵌套目录树）

    支持功能：
    - 完整的嵌套树结构显示
    - 按类型排序（目录优先）
    - 支持排除模式过滤
    - ZIP和仓库项目都支持

    参数:
    - id: 项目ID
    - exclude_patterns: JSON 格式的排除模式数组

    返回:
    - root: 文件树根节点，包含嵌套的children

    树节点字段:
    - name: 文件/目录名称
    - path: 相对路径
    - type: "file" 或 "directory"
    - size: 文件大小（仅文件有值）
    - children: 子节点列表（仅目录有值）
    """
    project = await db.get(Project, id)
    _raise_if_project_hidden(project)

    # Check permissions

    # 解析排除模式
    parsed_exclude_patterns = []
    if exclude_patterns:
        try:
            parsed_exclude_patterns = json.loads(exclude_patterns)
        except json.JSONDecodeError:
            pass

    if project.source_type == "zip":
        # 处理ZIP项目 - 直接从ZIP构建树
        zip_path = await load_project_zip(id)
        if not zip_path or not os.path.exists(zip_path):
            raise HTTPException(status_code=404, detail="项目文件不存在")

        try:
            loop = asyncio.get_event_loop()
            root_node = await loop.run_in_executor(None, _build_file_tree_from_zip, zip_path)
            return FileTreeResponse(root=root_node)
        except Exception as e:
            logger.error(f"构建ZIP文件树失败: {e}", exc_info=True)
            raise HTTPException(status_code=500, detail=f"无法构建文件树: {str(e)}")

    else:
        raise HTTPException(status_code=400, detail="仅支持ZIP类型项目")


@router.get("/{id}/files/{file_path:path}", response_model=Optional[FileContentResponse])
async def get_project_file_content(
    id: str,
    file_path: str,
    encoding: str = Query("utf-8", description="文件编码，默认为 utf-8"),
    use_cache: bool = Query(True, description="是否使用缓存"),
    stream: bool = Query(False, description="大文件是否流式传输"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(deps.get_current_user),
) -> Any:
    """
    异步获取 ZIP 项目中单个文件的完整内容

    支持功能：
    - 异步读取，避免阻塞事件循环
    - 内存缓存，加速重复访问
    - 大文件流式传输（>1MB）
    - 二进制文件智能检测
    - 多种编码支持

    参数:
    - id: 项目ID
    - file_path: ZIP内的文件相对路径（如 src/main.py）
    - encoding: 文本编码方式，默认 utf-8
    - use_cache: 是否使用缓存，默认True
    - stream: 强制使用流式传输（>1MB自动启用）

    返回:
    - file_path: 文件路径
    - content: 文件内容（字符串）
    - size: 文件字节大小
    - encoding: 使用的编码方式
    - is_text: 是否为文本文件
    - is_cached: 是否从缓存读取
    - created_at: 文件创建时间

    错误:
    - 404: 项目不存在或文件不存在
    - 400: 项目不是ZIP类型，或文件路径无效
    - 413: 文件过大（>50MB）
    """
    # 1. 验证项目存在
    project = await db.get(Project, id)
    _raise_if_project_hidden(project)

    # 2. 检查是否为ZIP项目
    if project.source_type != "zip":
        raise HTTPException(status_code=400, detail="仅支持ZIP类型项目")

    # 3. 验证文件路径
    validated_path = _validate_zip_file_path(file_path)

    # 4. 获取ZIP文件路径和哈希
    zip_path = await load_project_zip(id)
    if not zip_path or not os.path.exists(zip_path):
        raise HTTPException(status_code=404, detail="项目文件不存在")

    loop = asyncio.get_event_loop()
    known_relative_paths = await loop.run_in_executor(None, collect_zip_relative_paths, zip_path)
    resolved_zip_path = resolve_zip_member_path(validated_path, known_relative_paths)
    if not resolved_zip_path:
        raise HTTPException(status_code=404, detail=f"文件不存在: {validated_path}")

    zip_hash = _calculate_zip_file_hash(zip_path)

    # 5. 获取缓存管理器
    cache_manager = get_zip_cache_manager()

    try:
        # 6. 尝试从缓存读取（仅用于文本文件）
        cached_entry = None
        is_cached = False

        if use_cache:
            cached_entry = await cache_manager.get(id, resolved_zip_path, zip_hash)
            if cached_entry is not None and cached_entry.is_text:
                logger.info(f"从缓存读取文件: {resolved_zip_path}")
                is_cached = True
                return FileContentResponse(
                    file_path=resolved_zip_path,
                    content=cached_entry.content,
                    size=cached_entry.size,
                    encoding=cached_entry.encoding,
                    is_text=cached_entry.is_text,
                    is_cached=is_cached,
                    created_at=datetime.fromtimestamp(cached_entry.created_at, tz=timezone.utc),
                )

        # 7. 使用异步操作读取ZIP中的文件
        # 运行阻塞操作在线程池中，避免阻塞事件循环
        def _read_from_zip() -> tuple:
            with zipfile.ZipFile(zip_path, "r") as zf:
                try:
                    info = zf.getinfo(resolved_zip_path)
                except KeyError:
                    raise HTTPException(status_code=404, detail=f"文件不存在: {resolved_zip_path}")

                # 8. 检查文件大小
                MAX_FILE_SIZE = 50 * 1024 * 1024  # 50MB
                if info.file_size > MAX_FILE_SIZE:
                    raise HTTPException(
                        status_code=413,
                        detail=f"文件过大 ({info.file_size / 1024 / 1024:.2f}MB)，最大限制为 {MAX_FILE_SIZE / 1024 / 1024:.0f}MB",
                    )

                file_bytes = zf.read(resolved_zip_path)
                created_at = datetime(*info.date_time, tzinfo=timezone.utc)
                return file_bytes, info.file_size, created_at

        # 在线程池执行阻塞操作
        file_bytes, file_size, created_at = await loop.run_in_executor(None, _read_from_zip)

        # 9. 检测文件类型
        is_binary = _is_binary_file(resolved_zip_path, file_bytes[:1024])

        # 10. 大文件使用流式传输
        STREAM_THRESHOLD = 1 * 1024 * 1024  # 1MB阈值
        if stream or (file_size > STREAM_THRESHOLD):
            logger.info(
                f"使用流式传输读取文件: {resolved_zip_path} (大小: {file_size / 1024:.1f}KB)"
            )

            async def file_stream():
                """异步流式生成文件内容"""
                if is_binary:
                    # 二进制文件：返回base64编码
                    encoded = base64.b64encode(file_bytes).decode("ascii")
                    yield f'{{"file_path": "{resolved_zip_path}", "content": "{encoded}", "encoding": "base64", "size": {file_size}, "is_binary": true}}'
                else:
                    # 文本文件：返回JSON格式

                    # 解码文本
                    try:
                        content = file_bytes.decode(encoding)
                        actual_encoding = encoding
                    except (UnicodeDecodeError, LookupError):
                        try:
                            content = file_bytes.decode("utf-8")
                            actual_encoding = "utf-8"
                        except UnicodeDecodeError:
                            content = file_bytes.decode("latin-1")
                            actual_encoding = "latin-1"

                    response_data = {
                        "file_path": resolved_zip_path,
                        "content": content,
                        "size": file_size,
                        "encoding": actual_encoding,
                        "is_text": True,
                        "is_cached": False,
                        "created_at": created_at.isoformat(),
                    }
                    yield json.dumps(response_data)

            return StreamingResponse(
                file_stream(),
                media_type="application/json",
                headers={
                    "X-File-Path": resolved_zip_path,
                    "X-File-Size": str(file_size),
                    "X-Is-Binary": str(is_binary),
                },
            )

        # 11. 小文件直接返回
        if is_binary:
            logger.info(f"返回二进制文件（不解码）: {resolved_zip_path}")
            # 对于二进制文件，返回base64编码
            content = base64.b64encode(file_bytes).decode("ascii")
            actual_encoding = "base64"
            is_text = False
        else:
            # 12. 文本文件：解码内容
            try:
                content = file_bytes.decode(encoding)
                actual_encoding = encoding
            except (UnicodeDecodeError, LookupError):
                try:
                    content = file_bytes.decode("utf-8")
                    actual_encoding = "utf-8"
                except UnicodeDecodeError:
                    content = file_bytes.decode("latin-1")
                    actual_encoding = "latin-1"

            is_text = True

        # 13. 尝试缓存文本文件内容
        if is_text and use_cache and file_size < 5 * 1024 * 1024:  # 5MB限制
            await cache_manager.set(
                id,
                resolved_zip_path,
                zip_hash,
                content,
                file_size,
                actual_encoding,
                is_text,
            )

        # 14. 返回结果
        return FileContentResponse(
            file_path=resolved_zip_path,
            content=content,
            size=file_size,
            encoding=actual_encoding,
            is_text=is_text,
            is_cached=is_cached,
            created_at=created_at,
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"读取文件 {resolved_zip_path} 失败: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"无法读取项目文件: {str(e)}")


@router.get("/cache/stats")
async def get_cache_stats(
    current_user: User = Depends(deps.get_current_user),
) -> Any:
    """
    获取文件缓存统计信息

    返回:
    - total_entries: 缓存条目总数
    - hits: 缓存命中次数
    - misses: 缓存未命中次数
    - hit_rate: 命中率百分比
    - evictions: 驱逐的条目数
    - memory_used_mb: 已使用内存（MB）
    - memory_limit_mb: 内存限制（MB）
    """
    cache_manager = get_zip_cache_manager()
    return cache_manager.get_stats()


@router.post("/cache/clear")
async def clear_cache(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(deps.get_current_user),
) -> Any:
    """
    清空所有文件缓存
    """
    cache_manager = get_zip_cache_manager()
    await cache_manager.clear_all()
    return {"message": "缓存已清空"}


@router.post("/{id}/cache/invalidate")
async def invalidate_project_cache(
    id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(deps.get_current_user),
) -> Any:
    """
    清除特定项目的缓存（更新ZIP后调用）

    Args:
        id: 项目ID

    Returns:
        清除的缓存条目数
    """
    project = await db.get(Project, id)
    _raise_if_project_hidden(project)

    zip_path = await load_project_zip(id)
    if not zip_path:
        raise HTTPException(status_code=404, detail="项目文件不存在")

    zip_hash = _calculate_zip_file_hash(zip_path)
    cache_manager = get_zip_cache_manager()
    deleted_count = await cache_manager.invalidate(id, zip_hash)

    return {"message": "缓存已清除", "deleted_entries": deleted_count}
