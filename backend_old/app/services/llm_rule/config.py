from dataclasses import dataclass, field
from pathlib import Path
from .cache_manager import CacheManager


@dataclass
class Config:
    rules_dir: Path = Path(__file__).parent / "rules"
    generated_rules_dir: Path = Path(__file__).parent / "generated_rules"
    patches_dir: Path = Path(__file__).parent / "patches"
    repos_cache_dir: Path = Path(__file__).parent / "cache/repos"
    max_files_changed: int = 1
    max_retries: int = 8
    cache_manager: CacheManager = field(init=False)

    def __post_init__(self):
        self.cache_manager = CacheManager(self.repos_cache_dir)
