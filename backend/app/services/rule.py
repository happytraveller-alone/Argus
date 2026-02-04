import asyncio
import logging
import re
import shutil
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import yaml

from app.schemas.opengrep import OpengrepRuleCreateRequest
from app.core.config import settings

from .llm_rule.config import Config
from .llm_rule.git_manager import GitManager
from .llm_rule.llm_client import LLMClient
from .llm_rule.patch_processor import PatchInfo, PatchProcessor
from .llm_rule.rule_manager import RuleManager
from .llm_rule.rule_validator import RuleValidator


class AutoGrep:
    def __init__(self, config: Config):
        self.config = config
        self.rule_manager = RuleManager(config)
        self.patch_processor = PatchProcessor(config)
        self.rule_validator = RuleValidator(config)
        self.git_manager = GitManager(config)
        self.llm_client = LLMClient()

    async def process_patch(self, patch_file: Path) -> Optional[Dict[str, Any]]:
        """Process a single patch file with improved rule checking."""
        repo_path = None
        patch_info = None
        attempts: List[Dict[str, Any]] = []
        # Check if patch has already been processed
        if self.config.cache_manager.is_patch_processed(patch_file.name):
            logging.info(f"Skipping already processed patch: {patch_file.name}")
            return None

        try:
            patch_info = await asyncio.to_thread(self.patch_processor.process_patch, patch_file)
            if not patch_info:
                self.config.cache_manager.mark_patch_processed(patch_file.name)
                logging.warning(f"Failed to process patch file: {patch_file}")
                return {
                    "rule": None,
                    "patch_info": None,
                    "attempts": [],
                    "validation": {
                        "is_valid": False,
                        "message": "Failed to process patch file",
                    },
                }

            # Check if repo is known to fail
            repo_key = f"{patch_info.repo_owner}/{patch_info.repo_name}"
            if self.config.cache_manager.is_repo_failed(repo_key):
                error = self.config.cache_manager.get_repo_error(repo_key)
                logging.warning(f"Skipping known failed repository {repo_key}: {error}")
                self.config.cache_manager.mark_patch_processed(patch_file.name)
                return {
                    "rule": None,
                    "patch_info": patch_info,
                    "attempts": [],
                    "validation": {
                        "is_valid": False,
                        "message": f"Skipping known failed repository {repo_key}: {error}",
                    },
                }

            # Prepare repository
            repo_path = await asyncio.to_thread(self.git_manager.prepare_repo, patch_info)
            if not repo_path:
                self.config.cache_manager.mark_repo_failed(repo_key, "Failed to prepare repository")
                self.config.cache_manager.mark_patch_processed(patch_file.name)
                return {
                    "rule": None,
                    "patch_info": patch_info,
                    "attempts": [],
                    "validation": {
                        "is_valid": False,
                        "message": "Failed to prepare repository",
                    },
                }

            # Get the language from patch info
            language = patch_info.file_changes[0].language

            # Check if any existing rules can detect this vulnerability
            existing_rules = self.rule_manager.rules.get(language, [])
            is_detected, detecting_rule = await asyncio.to_thread(
                self.rule_validator.check_existing_rules,
                patch_info,
                repo_path,
                existing_rules,
            )

            if is_detected:
                logging.info(f"Vulnerability already detectable by existing rule: {detecting_rule}")
                self.config.cache_manager.mark_patch_processed(patch_file.name)
                return {
                    "rule": None,
                    "patch_info": patch_info,
                    "attempts": [],
                    "validation": {
                        "is_valid": False,
                        "message": "Vulnerability already detectable by existing rule",
                    },
                }

            # Initialize error tracking
            error_msg = None

            # Try generating and validating rule
            for attempt in range(self.config.max_retries):
                logging.info(
                    f"Attempt {attempt + 1}/{self.config.max_retries} for patch {patch_file}"
                )

                rule = await self.llm_client.generate_rule(patch_info, error_msg)
                if not rule:
                    error_msg = "Failed to generate valid rule structure"
                    attempts.append(
                        {
                            "attempt": attempt + 1,
                            "rule": None,
                            "validation": {"is_valid": False, "message": error_msg},
                        }
                    )
                    continue

                is_valid, validation_error = await asyncio.to_thread(
                    self.rule_validator.validate_rule,
                    rule,
                    patch_info,
                    repo_path,
                )

                if is_valid:
                    attempts.append(
                        {
                            "attempt": attempt + 1,
                            "rule": rule,
                            "validation": {"is_valid": True, "message": None},
                        }
                    )
                    logging.info(f"Successfully generated valid rule for {patch_file}")
                    self.config.cache_manager.mark_patch_processed(patch_file.name)
                    return {
                        "rule": rule,
                        "patch_info": patch_info,
                        "attempts": attempts,
                        "validation": {"is_valid": True, "message": None},
                    }

                # If validation failed due to parse errors, skip this patch
                attempts.append(
                    {
                        "attempt": attempt + 1,
                        "rule": rule,
                        "validation": {"is_valid": False, "message": validation_error},
                    }
                )

                if validation_error and (
                    "Parse error" in validation_error
                    or "Syntax error" in validation_error
                    or "Skipped all files" in validation_error
                ):
                    logging.info(f"Skipping patch due to parse errors: {validation_error}")
                    self.config.cache_manager.mark_patch_processed(patch_file.name)
                    return {
                        "rule": None,
                        "patch_info": patch_info,
                        "attempts": attempts,
                        "validation": {"is_valid": False, "message": validation_error},
                    }

                # Otherwise, use the error message for the next attempt
                error_msg = validation_error
                logging.warning(f"Attempt {attempt + 1} failed: {error_msg}")

            self.config.cache_manager.mark_patch_processed(patch_file.name)
            return {
                "rule": None,
                "patch_info": patch_info,
                "attempts": attempts,
                "validation": {"is_valid": False, "message": error_msg},
            }

        except Exception as e:
            logging.error(f"Unexpected error processing patch {patch_file}: {e}", exc_info=True)
            self.config.cache_manager.mark_patch_processed(patch_file.name)
            return {
                "rule": None,
                "patch_info": patch_info,
                "attempts": attempts,
                "validation": {"is_valid": False, "message": str(e)},
            }
        finally:
            # Always reset the repository state if it exists
            if repo_path and repo_path.exists():
                if not self.git_manager.reset_repo(repo_path):
                    logging.warning(f"Failed to reset repository state for: {repo_path}")
                    # If reset fails, we might want to force cleanup
                    self.git_manager.cleanup_repo(repo_path)

    async def _process_repo_patches(self, patches: list) -> list:
        """Process all patches for a single repository with caching."""
        rules = []
        for patch_file in patches:
            try:
                result = await self.process_patch(patch_file)
                if result:  # Check if we got a valid result
                    rule = result.get("rule")
                    patch_info = result.get("patch_info")
                    if rule and patch_info and patch_info.file_changes:
                        language = patch_info.file_changes[0].language
                        # Add language field to rule if not present
                        if "language" not in rule:
                            rule["language"] = language
                        # Store the rule immediately after generation
                        self.rule_manager.add_generated_rule(language, rule)
                        rules.append(rule)
                        logging.info(f"Successfully stored rule for {patch_file} in {language}")
            except Exception as e:
                logging.error(f"Error processing patch {patch_file}: {e}", exc_info=True)
        return rules

    async def run(self):
        """Main execution flow with caching."""
        logging.info("Starting AutoGrep processing with caching...")
        # Load initial rules
        self.rule_manager.load_initial_rules()
        # Get all patch files
        patch_files = list(self.config.patches_dir.glob("*.patch"))

        # Group patches by repository
        repo_patches = {}
        for patch_file in patch_files:
            # Skip if already processed
            if self.config.cache_manager.is_patch_processed(patch_file.name):
                logging.info(f"Skipping already processed patch: {patch_file.name}")
                continue
            logging.info(f"Processing patch file: {patch_file}")
            try:
                # Try to parse the patch filename to get repo info
                repo_owner, repo_name, _ = self.patch_processor.parse_patch_filename(
                    patch_file.name
                )
                repo_key = f"{repo_owner}/{repo_name}"

                # Skip if repo is known to fail
                if self.config.cache_manager.is_repo_failed(repo_key):
                    error = self.config.cache_manager.get_repo_error(repo_key)
                    logging.warning(f"Skipping known failed repository {repo_key}: {error}")
                    self.config.cache_manager.mark_patch_processed(patch_file.name)
                    continue

                if repo_key not in repo_patches:
                    repo_patches[repo_key] = []
                repo_patches[repo_key].append(patch_file)
            except ValueError as e:
                logging.error(f"Error parsing patch filename {patch_file}: {e}")
                self.config.cache_manager.mark_patch_processed(patch_file.name)
                continue

        # Process different repos in parallel using asyncio
        repo_tasks = []
        for repo_key, patches in repo_patches.items():
            task = self._process_repo_patches(patches)
            repo_tasks.append(task)

        # Wait for all repos to complete
        if repo_tasks:
            results = await asyncio.gather(*repo_tasks, return_exceptions=True)
            for result in results:
                if isinstance(result, Exception):
                    logging.error(f"Error processing repository patches: {result}")


async def get_rule_by_patch(request: OpengrepRuleCreateRequest) -> Dict[str, Any]:
    import tempfile
    from .llm_rule.repo_cache_manager import GlobalRepoCacheManager
    
    repo_owner = request.repo_owner
    repo_name = request.repo_name
    commit_hash = request.commit_hash
    commit_content = request.commit_content

    # 创建临时目录来存储 patch 和生成的规则
    # 注意: Git 克隆缓存会保留在全局缓存中，不在这个临时目录中
    temp_dir = tempfile.mkdtemp(prefix="patch_rule_")
    
    try:
        # 创建临时patch文件
        temp_patches_dir = Path(temp_dir) / "patches"
        temp_patches_dir.mkdir(parents=True, exist_ok=True)
        
        temp_file = temp_patches_dir / f"github.com_{repo_owner}_{repo_name}_{commit_hash}.patch"
        temp_file.write_text(commit_content)

        # 检查是否有现有的项目缓存
        cached_repo_dir = GlobalRepoCacheManager.get_repo_cache(repo_owner, repo_name)
        
        # 创建Config并指向合适的目录
        config = Config(
            max_files_changed=1,
            max_retries=3,
        )
        # 使用全局缓存或创建新的临时缓存目录
        if cached_repo_dir:
            # 使用现有的全局缓存
            config.repos_cache_dir = cached_repo_dir.parent
            logging.info(f"使用现有项目缓存: {cached_repo_dir}")
        else:
            # 创建临时缓存目录，后续会注册到全局缓存
            config.repos_cache_dir = Path(temp_dir) / "cache" / "repos"
            config.repos_cache_dir.mkdir(parents=True, exist_ok=True)
        
        config.patches_dir = temp_patches_dir
        config.generated_rules_dir = Path(temp_dir) / "generated_rules"
        config.rules_dir = Path(temp_dir) / "rules"
        # 重新初始化 cache_manager
        config.cache_manager = config.cache_manager.__class__(config.repos_cache_dir)

        # 创建所有必要的目录
        config.generated_rules_dir.mkdir(parents=True, exist_ok=True)
        config.repos_cache_dir.mkdir(parents=True, exist_ok=True)
        config.rules_dir.mkdir(parents=True, exist_ok=True)
        
        try:
            autogen = AutoGrep(config)
            logging.info("Starting AutoGrep run for single patch...")
            result = await autogen.process_patch(temp_file)

            # 如果这是一个新克隆的项目，注册到全局缓存
            if not cached_repo_dir:
                repo_cache_path = config.repos_cache_dir / f"{repo_owner}_{repo_name}".replace("/", "_")
                if repo_cache_path.exists():
                    # 如果是从临时目录克隆的，需要移动到全局缓存位置
                    global_cache_base = Path(settings.CACHE_DIR) / "repos"
                    global_cache_base.mkdir(parents=True, exist_ok=True)
                    global_repo_cache = global_cache_base / f"{repo_owner}_{repo_name}".replace("/", "_")
                    
                    if not global_repo_cache.exists():
                        try:
                            # 尝试将临时缓存移动到全局位置
                            shutil.move(str(repo_cache_path), str(global_repo_cache))
                            logging.info(f"已移动项目缓存到全局位置: {global_repo_cache}")
                            GlobalRepoCacheManager.register_repo_cache(repo_owner, repo_name, global_repo_cache)
                        except Exception as e:
                            logging.warning(f"无法移动缓存到全局位置: {e}，保留在临时位置")
                            GlobalRepoCacheManager.register_repo_cache(repo_owner, repo_name, repo_cache_path)
                    else:
                        # 全局位置已存在，清理临时的
                        shutil.rmtree(repo_cache_path, ignore_errors=True)
                        logging.info(f"全局缓存已存在，使用现有缓存")

            if result:
                patch_info = result.get("patch_info")
                language = None
                if patch_info and patch_info.file_changes:
                    language = patch_info.file_changes[0].language

                return {
                    "rule": result.get("rule"),
                    "validation": result.get("validation"),
                    "attempts": result.get("attempts", []),
                    "meta": {
                        "repo_owner": repo_owner,
                        "repo_name": repo_name,
                        "commit_hash": commit_hash,
                        "language": language,
                    },
                }

            return {
                "rule": None,
                "validation": {"is_valid": False, "message": "大模型生成规则失败，请稍后重试"},
                "attempts": [],
                "meta": {
                    "repo_owner": repo_owner,
                    "repo_name": repo_name,
                    "commit_hash": commit_hash,
                    "language": None,
                },
            }
        except Exception as e:
            logging.error(f"Error running AutoGrep: {e}", exc_info=True)
            return {
                "rule": None,
                "validation": {"is_valid": False, "message": "生成失败"},
                "attempts": [],
                "meta": {
                    "repo_owner": repo_owner,
                    "repo_name": repo_name,
                    "commit_hash": commit_hash,
                    "language": None,
                },
            }
    finally:
        # 清理临时目录（但保留全局缓存中的 git 克隆）
        if Path(temp_dir).exists():
            shutil.rmtree(temp_dir, ignore_errors=True)
            logging.info(f"Cleaned up temporary directory: {temp_dir}")


def _normalize_rule_yaml(
    rule_yaml: str, llm_client: LLMClient
) -> Tuple[Optional[str], Optional[dict], Optional[str]]:
    cleaned = llm_client.clean_yaml_text(rule_yaml)
    if not cleaned:
        return None, None, "规则YAML格式错误"
    try:
        data = yaml.safe_load(cleaned) or {}
    except yaml.YAMLError:
        return None, None, "规则YAML解析失败"

    rules = data.get("rules")
    if not isinstance(rules, list) or not rules:
        return None, None, "规则中未找到有效的 rules 列表"

    rule = rules[0]
    if isinstance(rule, list) and rule:
        rule = rule[0]
    if not isinstance(rule, dict):
        return None, None, "规则结构不合法"

    return cleaned, rule, None


def _validate_rule_schema_generic(rule: dict) -> Tuple[bool, Optional[str]]:
    if not isinstance(rule, dict):
        return False, "规则结构不合法"

    required_fields = ["id", "message", "severity", "languages"]
    missing_fields = [field for field in required_fields if field not in rule]
    if missing_fields:
        return False, f"缺少必填字段: {', '.join(missing_fields)}"

    pattern_fields = ["pattern", "patterns", "pattern-either", "pattern-regex"]
    if not any(field in rule for field in pattern_fields):
        return False, "缺少模式字段: pattern/patterns/pattern-either/pattern-regex"

    valid_severities = ["ERROR", "WARNING", "INFO"]
    if rule.get("severity") not in valid_severities:
        return False, f"严重程度必须为: {', '.join(valid_severities)}"

    rule_id = str(rule.get("id") or "").strip()
    if not rule_id:
        return False, "规则ID不能为空"
    # Keep '-' at the end of the char class to avoid range ambiguity.
    if not re.match(r"^[a-z0-9._-]+$", rule_id):
        return False, "规则ID只能包含小写字母、数字、-、_、."

    languages = rule.get("languages")
    if not isinstance(languages, list) or not languages:
        return False, "languages 必须为非空列表"

    return True, None


async def validate_generic_rule(rule_yaml: str) -> Dict[str, Any]:
    llm_client = LLMClient()
    cleaned, rule, error = _normalize_rule_yaml(rule_yaml, llm_client)
    if error:
        return {
            "rule": None,
            "rule_yaml": None,
            "test_yaml": None,
            "validation": {"is_valid": False, "message": error},
        }

    is_valid, validation_error = _validate_rule_schema_generic(rule)
    if not is_valid:
        return {
            "rule": rule,
            "rule_yaml": cleaned,
            "test_yaml": None,
            "validation": {"is_valid": False, "message": validation_error},
        }

    return {
        "rule": rule,
        "rule_yaml": cleaned,
        "test_yaml": None,
        "validation": {"is_valid": True, "message": None},
    }
