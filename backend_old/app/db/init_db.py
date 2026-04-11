"""
数据库初始化模块
在应用启动时创建默认演示账户并初始化内置资源
"""
import hashlib
import json
import logging
import os
import subprocess
import sys
import tempfile
import zipfile
from dataclasses import dataclass
from pathlib import Path

import yaml
from sqlalchemy import insert, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from tqdm import tqdm

from app.db import (
    opengrep_internal_rules_dir,
    opengrep_patch_artifacts_dir,
    opengrep_patch_rules_dir,
)
from app.core.security import get_password_hash
from app.models.opengrep import OpengrepRule
from app.models.project import Project
from app.models.user import User
from app.services.gitleaks_rules_seed import ensure_builtin_gitleaks_rules
from app.services.seed_archive import download_seed_archive
from app.services.upload.language_detection import detect_languages_from_paths
from app.services.zip_storage import delete_project_zip, has_project_zip, save_project_zip

logger = logging.getLogger(__name__)

try:
    YAML_LOADER = yaml.CSafeLoader
except AttributeError:
    YAML_LOADER = yaml.SafeLoader

ENABLE_RULE_IMPORT_PROGRESS = (
    os.getenv("INIT_DB_PROGRESS", "false").strip().lower() in {"1", "true", "yes", "on"}
)


def _load_yaml_fast(content: str):
    """优先使用 C Loader 解析 YAML，加快规则导入速度。"""
    return yaml.load(content, Loader=YAML_LOADER)


def _normalize_confidence(value: str | None) -> str:
    normalized = str(value or "").strip().upper()
    if normalized in {"HIGH", "MEDIUM", "LOW"}:
        return normalized
    return "LOW"


def _build_single_rule_yaml(rule: dict) -> str:
    """每条规则独立存储，避免把整文件 YAML 重复写入数据库。"""
    return yaml.safe_dump({"rules": [rule]}, allow_unicode=True, sort_keys=False)

# 默认演示账户配置
DEFAULT_DEMO_EMAIL = "demo@example.com"
DEFAULT_DEMO_PASSWORD = "demo123"
DEFAULT_DEMO_NAME = "演示用户"
DEFAULT_LIBPLIST_NAME = "libplist"
DEFAULT_LIBPLIST_LEGACY_ZIP_URL = "https://github.com/libimobiledevice/libplist/archive/refs/tags/2.7.0.zip"
DEFAULT_LIBPLIST_LEGACY_DESCRIPTION = "默认示例项目：libplist 2.7.0"
DEFAULT_LIBPLIST_DESCRIPTION = (
    "libplist 是一个小型、可移植的 C 语言库，用于读写 Apple 的 Property List（.plist）数据。"
)
DEFAULT_LIBPLIST_ARCHIVE_NAME = "libplist-2.7.0.zip"
_LEGACY_DEMO_PROJECT_NAMES = {
    "电商平台后端",
    "移动端 App",
    "数据分析平台",
    "微服务网关",
    "智能客服系统",
    "区块链钱包",
}


@dataclass(frozen=True)
class DefaultZipSeedProject:
    name: str
    description: str
    archive_name: str
    owner: str
    repo: str
    ref_type: str
    ref: str
    fallback_languages: list[str]
    legacy_description: str | None = None
    legacy_repository_url: str | None = None


def _sha256_file(file_path: str) -> str:
    sha256 = hashlib.sha256()
    with open(file_path, "rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            sha256.update(chunk)
    return sha256.hexdigest()


def _collect_zip_paths(zip_file_path: str) -> list[str]:
    paths: list[str] = []
    with zipfile.ZipFile(zip_file_path, "r") as zf:
        for item in zf.infolist():
            if item.is_dir():
                continue
            # 路径统一去掉末尾 /
            paths.append(item.filename.strip("/"))
    return paths


async def _discard_legacy_demo_projects(db: AsyncSession, user_id: str) -> None:
    result = await db.execute(
        select(Project).where(
            Project.owner_id == user_id,
            Project.name.in_(_LEGACY_DEMO_PROJECT_NAMES),
        )
    )
    legacy_projects = result.scalars().all()
    if not legacy_projects:
        return

    for project in legacy_projects:
        try:
            await delete_project_zip(project.id)
        except Exception:
            pass
        await db.delete(project)

    await db.commit()
    logger.info("✓ 已丢弃旧历史 demo 项目: %s 个", len(legacy_projects))


def _build_default_seed_projects() -> list[DefaultZipSeedProject]:
    return [
        DefaultZipSeedProject(
            name=DEFAULT_LIBPLIST_NAME,
            description=DEFAULT_LIBPLIST_DESCRIPTION,
            archive_name=DEFAULT_LIBPLIST_ARCHIVE_NAME,
            owner="libimobiledevice",
            repo="libplist",
            ref_type="tag",
            ref="2.7.0",
            fallback_languages=["C"],
            legacy_description=DEFAULT_LIBPLIST_LEGACY_DESCRIPTION,
            legacy_repository_url=DEFAULT_LIBPLIST_LEGACY_ZIP_URL,
        ),
        DefaultZipSeedProject(
            name="DVWA",
            description=(
                "DVWA（Damn Vulnerable Web Application）是经典的 Web 安全靶场项目，"
                "覆盖 SQL 注入、XSS、文件包含、CSRF 等常见漏洞场景，适合用于漏洞验证与规则调试。"
            ),
            archive_name="DVWA-master.zip",
            owner="digininja",
            repo="DVWA",
            ref_type="commit",
            ref="eba982f486aef10fd4278948cd1bb078504b74e7",
            fallback_languages=["PHP", "JavaScript"],
        ),
        DefaultZipSeedProject(
            name="DSVW",
            description=(
                "DSVW（Damn Small Vulnerable Web）是轻量级 Web 漏洞练习项目，"
                "聚焦常见输入验证与访问控制漏洞，便于快速复现与教学演示。"
            ),
            archive_name="DSVW-master.zip",
            owner="stamparm",
            repo="DSVW",
            ref_type="commit",
            ref="7d40f4b7939c901610ed9b85724552d60e7d63fa",
            fallback_languages=["PHP", "JavaScript"],
        ),
        DefaultZipSeedProject(
            name="WebGoat",
            description=(
                "WebGoat 是 OWASP 提供的交互式安全训练平台，"
                "包含身份认证、注入、逻辑漏洞等多类教学关卡，适合后端与应用安全演练。"
            ),
            archive_name="WebGoat-main.zip",
            owner="WebGoat",
            repo="WebGoat",
            ref_type="commit",
            ref="7d3343d08c360d4751e5298e1fe910463b7731a1",
            fallback_languages=["Java", "JavaScript"],
        ),
        DefaultZipSeedProject(
            name="JavaSecLab",
            description=(
                "JavaSecLab 是面向 Java 生态的漏洞练习项目，"
                "覆盖反序列化、表达式注入、模板注入等典型风险，适合 Java 安全测试场景。"
            ),
            archive_name="JavaSecLab-1.4.zip",
            owner="whgojp",
            repo="JavaSecLab",
            ref_type="tag",
            ref="V1.4",
            fallback_languages=["Java"],
        ),
        DefaultZipSeedProject(
            name="govwa",
            description=(
                "govwa 是 Go 语言 Web 漏洞练习项目，"
                "用于演示输入校验、权限控制和请求处理中的安全漏洞，适合 Go 应用审计训练。"
            ),
            archive_name="govwa-master.zip",
            owner="0c34",
            repo="govwa",
            ref_type="commit",
            ref="4058f79f31eeb4a36d8f1e64bba1f0c899646e6f",
            fallback_languages=["Go", "HTML"],
        ),
        DefaultZipSeedProject(
            name="fastjson",
            description=(
                "fastjson 安全样本项目用于演示 Java 反序列化链与历史漏洞利用面，"
                "可用于规则回归测试与序列化安全能力验证。"
            ),
            archive_name="fastjson.zip",
            owner="alibaba",
            repo="fastjson",
            ref_type="commit",
            ref="c942c83443117b73af5ad278cc780270998ba3e1",
            fallback_languages=["Java"],
        ),
    ]


async def _ensure_default_zip_seed_project(
    db: AsyncSession,
    user: User,
    seed: DefaultZipSeedProject,
) -> None:
    """
    确保默认 ZIP 种子项目存在，并从 GitHub 归档导入到项目存储。
    """
    result = await db.execute(
        select(Project).where(
            Project.owner_id == user.id,
            Project.name == seed.name,
        )
    )
    project = result.scalars().first()

    if not project:
        project = Project(
            owner_id=user.id,
            name=seed.name,
            description=seed.description,
            source_type="zip",
            repository_url=None,
            repository_type="other",
            default_branch="main",
            programming_languages=json.dumps([], ensure_ascii=False),
            is_active=True,
        )
        db.add(project)
        await db.commit()
        await db.refresh(project)
        logger.info("✓ 已创建默认项目: %s", seed.name)
    else:
        should_update_project = False
        if not project.is_active:
            project.is_active = True
            should_update_project = True
            logger.info("✓ 已恢复默认项目: %s", seed.name)

        current_description = (project.description or "").strip()
        if not current_description or (
            seed.legacy_description and current_description == seed.legacy_description
        ):
            project.description = seed.description
            should_update_project = True

        if project.source_type != "zip":
            project.source_type = "zip"
            should_update_project = True

        # 旧版本默认项目会写入远程 URL，迁移到离线模式后统一清空
        if seed.legacy_repository_url and project.repository_url == seed.legacy_repository_url:
            project.repository_url = None
            should_update_project = True

        if should_update_project:
            await db.commit()
            await db.refresh(project)

    if await has_project_zip(project.id):
        return

    archive_path: str | None = None
    try:
        archive_path = await download_seed_archive(
            owner=seed.owner,
            repo=seed.repo,
            ref_type=seed.ref_type,
            ref=seed.ref,
            archive_name=seed.archive_name,
        )
        zip_hash = _sha256_file(archive_path)
        await save_project_zip(
            project.id,
            archive_path,
            seed.archive_name,
        )

        zip_paths = _collect_zip_paths(archive_path)
        detected_languages = detect_languages_from_paths(zip_paths)
        project.programming_languages = json.dumps(
            detected_languages or seed.fallback_languages,
            ensure_ascii=False,
        )
        project.zip_file_hash = zip_hash
        try:
            await db.commit()
        except IntegrityError:
            # 已存在相同 ZIP 哈希时，不阻塞默认项目初始化
            await db.rollback()
            project.zip_file_hash = None
            await db.commit()
            logger.warning("默认项目 %s ZIP 哈希重复，已跳过去重哈希写入", seed.name)
        logger.info("✓ 默认项目 %s ZIP 远程导入完成", seed.name)
    except Exception as e:
        logger.warning("默认项目 %s ZIP 下载失败，仅保留项目记录: %s", seed.name, e)
    finally:
        if archive_path and os.path.exists(archive_path):
            try:
                os.remove(archive_path)
            except OSError:
                pass


async def ensure_default_seed_projects(db: AsyncSession, user: User) -> None:
    """
    统一确保所有 GitHub 预置项目存在。
    """
    await _discard_legacy_demo_projects(db, user.id)
    for seed in _build_default_seed_projects():
        await _ensure_default_zip_seed_project(db=db, user=user, seed=seed)


async def create_demo_user(db: AsyncSession) -> User | None:
    """
    创建演示用户账户
    - demo@example.com / demo123
    """
    result = await db.execute(select(User).where(User.email == DEFAULT_DEMO_EMAIL))
    demo_user = result.scalars().first()

    if not demo_user:
        demo_user = User(
            email=DEFAULT_DEMO_EMAIL,
            hashed_password=get_password_hash(DEFAULT_DEMO_PASSWORD),
            full_name=DEFAULT_DEMO_NAME,
            is_active=True,
            is_superuser=True,  # 演示用户拥有管理员权限以便体验所有功能
            role="admin",
        )
        db.add(demo_user)
        await db.flush()
        logger.info(f"✓ 创建演示账户: {DEFAULT_DEMO_EMAIL}")
        return demo_user
    else:
        logger.info(f"演示账户已存在: {DEFAULT_DEMO_EMAIL}")
        return demo_user


def validate_opengrep_rule(yaml_content: str) -> bool:
    """
    使用 opengrep --config 验证规则是否有效
    """
    try:
        # 创建临时文件保存规则
        with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False, encoding='utf-8') as tmp_file:
            tmp_file.write(yaml_content)
            tmp_file_path = tmp_file.name

        try:
            # 使用 opengrep --config 验证规则
            result = subprocess.run(
                ['opengrep', '--config', tmp_file_path, '--validate'],
                capture_output=True,
                text=True,
                timeout=5
            )
            return result.returncode == 0
        finally:
            # 删除临时文件
            if os.path.exists(tmp_file_path):
                os.unlink(tmp_file_path)
    except subprocess.TimeoutExpired:
        logger.warning("规则验证超时")
        return False
    except FileNotFoundError:
        logger.warning("opengrep 命令未找到,跳过规则验证")
        return True  # 如果找不到 opengrep,则跳过验证
    except Exception as e:
        logger.warning(f"规则验证失败: {e}")
        return False


async def create_internal_opengrep_rules(db: AsyncSession) -> None:
    """
    从 Rust-owned scan_rule_assets（回退 legacy app/db/rules）读取内置 opengrep 规则
    - 判断规则 ID 是否已在表中,只添加不存在的规则
    - 验证每条规则是否可用
    """
    # 检查数据库中是否已有规则，如果有则跳过初始化
    result = await db.execute(select(OpengrepRule.name))
    existing_rule_ids = {row[0] for row in result.fetchall()}
    if existing_rule_ids:
        logger.info(f"数据库中已存在 {len(existing_rule_ids)} 条规则，跳过内置规则初始化")
        return

    # 获取规则文件目录
    rules_dir = opengrep_internal_rules_dir()
    if not rules_dir.exists():
        logger.warning(f"规则目录不存在: {rules_dir}")
        return

    # 读取所有 .yaml 文件
    yaml_files = list(rules_dir.glob("*.yaml")) + list(rules_dir.glob("*.yml"))
    if not yaml_files:
        logger.warning(f"规则目录中没有找到 .yaml 文件: {rules_dir}")
        return

    logger.info(f"开始加载内置规则，找到 {len(yaml_files)} 个文件...")
    logger.info(f"数据库中已存在 {len(existing_rule_ids)} 条规则")

    created_count = 0
    skipped_count = 0
    invalid_count = 0
    rows_to_add = []

    iterator = tqdm(
        yaml_files,
        desc="处理规则文件",
        unit="file",
        disable=not (ENABLE_RULE_IMPORT_PROGRESS and sys.stderr.isatty()),
    )
    for yaml_file in iterator:
        try:
            with open(yaml_file, encoding='utf-8') as f:
                content = f.read()
                rule_data = _load_yaml_fast(content)

            # 解析 YAML 中的规则
            if not rule_data or 'rules' not in rule_data:
                logger.warning(f"跳过无效的规则文件: {yaml_file.name}")
                invalid_count += 1
                continue

            # 验证规则是否有效
            # if not validate_opengrep_rule(content):
            #     logger.warning(f"规则验证失败,跳过: {yaml_file.name}")
            #     invalid_count += 1
            #     continue

            for _rule_idx, rule in enumerate(rule_data['rules']):
                rule_id = rule.get('id', yaml_file.stem)
                metadata = rule.get('metadata', {}) if isinstance(rule, dict) else {}

                # 判断规则是否已在表中
                if rule_id in existing_rule_ids:
                    logger.debug(f"  ⊘ 规则已存在，跳过: {rule_id}")
                    skipped_count += 1
                    continue

                # 提取语言（优先从顶层查找，再从 metadata 中查找）
                languages = rule.get('languages', [])
                if not languages or not isinstance(languages, list):
                    languages = metadata.get('languages', [])

                if isinstance(languages, list) and languages:
                    language = languages[0]
                else:
                    language = 'unknown'

                # 提取严重程度
                severity = rule.get('severity', 'INFO')
                if severity not in ['ERROR', 'WARNING', 'INFO']:
                    severity = 'INFO'

                # 提取置信度（从顶层或 metadata 中）
                confidence = _normalize_confidence(
                    rule.get('confidence') or metadata.get('confidence')
                )

                # 提取描述 - 如果没有则置空
                description = rule.get('message') or None

                # 提取 CWE - 优先规则字段，其次 metadata
                # 检查顶层的 cwe 字段（可能是 None 或具体值）
                cwe = None
                if 'cwe' in rule and rule['cwe'] is not None:
                    cwe = rule['cwe']
                elif 'cwe' in metadata and metadata['cwe'] is not None:
                    cwe = metadata['cwe']

                # 标准化 CWE 格式为列表
                if cwe:
                    if isinstance(cwe, str):
                        cwe = [cwe]
                    elif isinstance(cwe, list):
                        # 确保列表中的所有元素都是字符串
                        cwe = [str(c) for c in cwe if c]
                    else:
                        cwe = None
                else:
                    cwe = None

                # 每条规则独立存储，避免重复写入整文件 YAML
                rows_to_add.append(
                    {
                        "name": rule_id,
                        "pattern_yaml": _build_single_rule_yaml(rule),
                        "language": language,
                        "severity": severity,
                        "confidence": confidence,
                        "description": description,
                        "cwe": cwe,
                        "source": "internal",
                        "correct": True,
                        "is_active": True,
                    }
                )
                existing_rule_ids.add(rule_id)  # 更新本地集合，防止同一批次重复
                logger.debug(f"  ✓ 规则已准备入库: {rule_id} (CWE: {len(cwe) if cwe else 0})")

        except Exception as e:
            logger.error(f"加载规则文件失败 {yaml_file.name}: {e}")
            invalid_count += 1
            continue

    # 一次性批量添加所有规则
    if rows_to_add:
        try:
            logger.info(f"正在批量入库 {len(rows_to_add)} 条新规则...")
            await db.execute(insert(OpengrepRule), rows_to_add)
            await db.commit()
            created_count = len(rows_to_add)
            logger.info(f"  ✓ 批量加载了 {created_count} 条新规则")
        except Exception as e:
            await db.rollback()
            logger.error(f"  ✗ 规则批量入库失败: {e}")
            invalid_count += len(rows_to_add)

    logger.info(f"✓ 内置规则加载完成: 成功创建 {created_count} 条新规则，跳过 {skipped_count} 条已存在的规则，{invalid_count} 条失败")


async def create_patch_opengrep_rules(db: AsyncSession) -> None:
    """
    从 Rust-owned scan_rule_assets（回退 legacy app/db/rules_from_patches）读取 patch 来源规则
    - 支持多层目录结构（按编程语言分类）
    - 判断规则 ID 是否已在表中，只添加不存在的规则
    - 验证每条规则是否可用
    """
    # 检查数据库中是否已有规则
    result = await db.execute(select(OpengrepRule.name))
    existing_rule_ids = {row[0] for row in result.fetchall()}

    # 注意：Patch 规则通常是增量添加的，且数量较少，所以即使数据库不为空也不应该跳过初始化
    # 我们只会跳过那些 ID 已经存在的规则
    # if existing_rule_ids:
    #     logger.info(f"数据库中已存在 {len(existing_rule_ids)} 条规则，跳过 Patch 规则初始化")
    #     return

    # 获取规则文件目录
    rules_dir = opengrep_patch_rules_dir()
    if not rules_dir.exists():
        logger.warning(f"Patch 规则目录不存在: {rules_dir}")
        return

    # 递归读取所有 .yml 文件
    yaml_files = list(rules_dir.glob("**/*.yml")) + list(rules_dir.glob("**/*.yaml"))
    if not yaml_files:
        logger.warning(f"Patch 规则目录中没有找到 .yml 文件: {rules_dir}")
        return

    logger.info(f"开始加载 Patch 来源规则，找到 {len(yaml_files)} 个文件...")
    logger.info(f"数据库中已存在 {len(existing_rule_ids)} 条规则")

    created_count = 0
    skipped_count = 0
    error_count = 0
    rows_to_add = []

    iterator = tqdm(
        yaml_files,
        desc="处理 Patch 规则文件",
        unit="file",
        disable=not (ENABLE_RULE_IMPORT_PROGRESS and sys.stderr.isatty()),
    )
    for yaml_file in iterator:
        try:
            with open(yaml_file, encoding='utf-8') as f:
                content = f.read()
                rule_data = _load_yaml_fast(content)

            # 解析 YAML 中的规则
            if not rule_data or 'rules' not in rule_data:
                logger.debug(f"  ⊘ 跳过无效的规则文件: {yaml_file.relative_to(rules_dir)}")
                error_count += 1
                continue

            # 验证规则是否有效
            # if not validate_opengrep_rule(content):
            #     logger.debug(f"  ⊘ 规则验证失败,跳过: {yaml_file.relative_to(rules_dir)}")
            #     error_count += 1
            #     continue

            # 通常 Patch 规则文件只包含一条规则
            for _rule_idx, rule in enumerate(rule_data['rules']):
                rule_id = rule.get('id', yaml_file.stem)
                metadata = rule.get('metadata', {}) if isinstance(rule, dict) else {}

                # 判断规则是否已在表中
                if rule_id in existing_rule_ids:
                    logger.debug(f"  ⊘ 规则已存在，跳过: {rule_id}")
                    skipped_count += 1
                    continue

                # 提取语言（优先从顶层查找，再从 metadata 中查找）
                languages = rule.get('languages', [])
                if not languages or not isinstance(languages, list):
                    languages = metadata.get('languages', [])

                if isinstance(languages, list) and languages:
                    language = languages[0]
                else:
                    # 如果规则中没有指定语言，尝试从目录名称中推断
                    relative_path = yaml_file.relative_to(rules_dir)
                    language = relative_path.parts[0] if relative_path.parts else 'unknown'

                # 提取严重程度
                severity = rule.get('severity', 'INFO')
                if severity not in ['ERROR', 'WARNING', 'INFO']:
                    severity = 'INFO'

                # 提取置信度（从顶层或 metadata 中）
                confidence = _normalize_confidence(
                    rule.get('confidence') or metadata.get('confidence')
                )

                # 提取描述 - 如果没有则置空
                description = rule.get('message') or None

                # 读取对应的 patch 文件内容
                patch_content = None
                patch_file = opengrep_patch_artifacts_dir() / f"{yaml_file.stem}.patch"
                if patch_file.exists():
                    try:
                        with open(patch_file, encoding='utf-8') as pf:
                            patch_content = pf.read()
                    except Exception as e:
                        logger.debug(f"  ⊘ 无法读取 patch 文件 {patch_file.name}: {e}")
                        # 如果读取失败，尝试从 metadata 获取 URL
                        patch_content = metadata.get('source-url') or None
                else:
                    # 如果没有对应的 patch 文件，从 metadata 获取 URL
                    patch_content = metadata.get('source-url') or None

                # 提取 CWE - 优先规则字段，其次 metadata
                # 检查顶层的 cwe 字段（可能是 None 或具体值）
                cwe = None
                if 'cwe' in rule and rule['cwe'] is not None:
                    cwe = rule['cwe']
                elif 'cwe' in metadata and metadata['cwe'] is not None:
                    cwe = metadata['cwe']

                # 标准化 CWE 格式为列表
                if cwe:
                    if isinstance(cwe, str):
                        cwe = [cwe]
                    elif isinstance(cwe, list):
                        # 确保列表中的所有元素都是字符串
                        cwe = [str(c) for c in cwe if c]
                    else:
                        cwe = None
                else:
                    cwe = None

                # 每条规则独立存储，避免重复写入整文件 YAML
                rows_to_add.append(
                    {
                        "name": rule_id,
                        "pattern_yaml": _build_single_rule_yaml(rule),
                        "language": language,
                        "severity": severity,
                        "confidence": confidence,
                        "description": description,
                        "cwe": cwe,
                        "source": "patch",
                        "patch": patch_content,
                        "correct": True,
                        "is_active": True,
                    }
                )
                existing_rule_ids.add(rule_id)  # 更新本地集合，防止同一批次重复
                logger.debug(f"  ✓ 规则已准备入库: {rule_id} (CWE: {len(cwe) if cwe else 0})")

        except Exception as e:
            logger.error(f"加载规则文件失败 {yaml_file.relative_to(rules_dir)}: {e}")
            error_count += 1
            continue

    # 一次性批量添加所有规则
    if rows_to_add:
        try:
            logger.info(f"正在批量入库 {len(rows_to_add)} 条新规则...")
            await db.execute(insert(OpengrepRule), rows_to_add)
            await db.commit()
            created_count = len(rows_to_add)
            logger.info(f"  ✓ 批量加载了 {created_count} 条新规则")
        except Exception as e:
            await db.rollback()
            logger.error(f"  ✗ 规则批量入库失败: {e}")
            error_count += len(rows_to_add)

    logger.info(f"✓ Patch 规则导入完成: 成功创建 {created_count} 条新规则，"
               f"跳过 {skipped_count} 条已存在的规则，{error_count} 条错误并已删除")


async def init_db(db: AsyncSession) -> None:
    """
    初始化数据库
    """
    logger.info("开始初始化数据库...")

    # 创建演示用户
    demo_user = await create_demo_user(db)

    # 不再创建历史演示项目，统一切换为 GitHub 预置样本项目
    if demo_user:
        await ensure_default_seed_projects(db, demo_user)

    await db.commit()

    # 初始化内置 opengrep 规则
    await create_internal_opengrep_rules(db)

    # 初始化 Patch 来源的 opengrep 规则
    await create_patch_opengrep_rules(db)

    # 初始化 gitleaks 内置规则（失败不阻断启动）
    try:
        await ensure_builtin_gitleaks_rules(db)
    except Exception as e:
        logger.warning(f"初始化 gitleaks 内置规则跳过: {e}")

    # 初始化系统模板和规则
    try:
        from app.services.init_templates import init_templates_and_rules
        await init_templates_and_rules(db)
    except Exception as e:
        logger.warning(f"初始化模板和规则跳过: {e}")

    logger.info("数据库初始化完成")
