import asyncio
from app.schemas.opengrep import OpengrepRuleCreateRequest
from pathlib import Path

from .llm_rule.config import Config
from .llm_rule.git_manager import GitManager
from .llm_rule.patch_processor import PatchProcessor, PatchInfo
from .llm_rule.rule_manager import RuleManager
from .llm_rule.rule_validator import RuleValidator
from .llm_rule.llm_client import LLMClient
import logging
from typing import Optional, Tuple, Dict, Any, List
import shutil


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
            patch_info = self.patch_processor.process_patch(patch_file)
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
            repo_path = self.git_manager.prepare_repo(patch_info)
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
            is_detected, detecting_rule = self.rule_validator.check_existing_rules(
                patch_info, repo_path, existing_rules
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

                is_valid, validation_error = self.rule_validator.validate_rule(
                    rule, patch_info, repo_path
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

    repo_owner = request.repo_owner
    repo_name = request.repo_name
    commit_hash = request.commit_hash
    commit_content = request.commit_content

    temp_file = (
        Path(__file__).parent
        / "llm_rule"
        / "patches"
        / f"github.com_{repo_owner}_{repo_name}_{commit_hash}.patch"
    )
    temp_file.write_text(commit_content)

    config = Config(
        max_files_changed=1,
        max_retries=3,
    )

    config.generated_rules_dir.mkdir(parents=True, exist_ok=True)
    config.repos_cache_dir.mkdir(parents=True, exist_ok=True)
    config.rules_dir.mkdir(parents=True, exist_ok=True)
    config.patches_dir.mkdir(parents=True, exist_ok=True)
    try:
        autogen = AutoGrep(config)
        logging.info("Starting AutoGrep run for single patch...")
        result = await autogen.process_patch(temp_file)

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
        if temp_file.exists():
            temp_file.unlink()
        shutil.rmtree(config.generated_rules_dir, ignore_errors=True)
        # shutil.rmtree(config.repos_cache_dir, ignore_errors=True)