from pathlib import Path

import git

from app.services.llm_rule.config import Config
from app.services.llm_rule.git_manager import GitManager
from app.services.llm_rule.patch_processor import PatchInfo


def test_prepare_repo_does_not_fallback_to_ssh_when_https_clone_fails(tmp_path, monkeypatch):
    attempted_urls = []

    monkeypatch.setattr(GitManager, "_check_git_installation", lambda self: None)

    def fake_clone_from(url, repo_path, progress=None):
        attempted_urls.append(url)
        raise git.exc.GitCommandError(
            ["git", "clone", url],
            128,
            stderr="https clone failed",
        )

    monkeypatch.setattr(
        "app.services.llm_rule.git_manager.get_mirror_candidates",
        lambda url: [url],
    )
    monkeypatch.setattr("app.services.llm_rule.git_manager.git.Repo.clone_from", fake_clone_from)

    manager = GitManager(Config(repos_cache_dir=Path(tmp_path) / "repos"))
    patch_info = PatchInfo(
        repo_owner="octo",
        repo_name="repo",
        commit_id="deadbeef",
        file_changes=[],
    )

    repo_path = manager.prepare_repo(patch_info)

    assert repo_path is None
    assert attempted_urls == ["https://github.com/octo/repo"]
