"""
Token Estimator - Token 计数器

默认使用无网络依赖的启发式估算，避免在请求关键路径上因为 tiktoken
冷启动或远程编码下载而阻塞首包响应。
"""

from __future__ import annotations

import logging
import os
from typing import Any, Optional

from app.core.config import settings

logger = logging.getLogger(__name__)

# tiktoken 编码器缓存
_encoders: dict[str, Any] = {}
_tiktoken_available: bool | None = None  # None=未检测, True=可用, False=不可用
_logged_method: bool = False  # 是否已输出使用方案日志
_runtime_mode: Optional[str] = None

_RUNTIME_MODE_HEURISTIC = "heuristic"
_RUNTIME_MODE_AUTO = "auto"
_RUNTIME_MODE_PRECISE = "precise"
_VALID_RUNTIME_MODES = {
    _RUNTIME_MODE_HEURISTIC,
    _RUNTIME_MODE_AUTO,
    _RUNTIME_MODE_PRECISE,
}


def _normalize_runtime_mode(value: Optional[str]) -> str:
    normalized = str(value or "").strip().lower()
    if normalized in _VALID_RUNTIME_MODES:
        return normalized
    return _RUNTIME_MODE_HEURISTIC


def get_runtime_token_counting_mode() -> str:
    """获取运行时 token 计数模式。"""
    global _runtime_mode

    if _runtime_mode is None:
        configured = os.getenv(
            "LLM_TOKEN_COUNTING_MODE",
            getattr(settings, "LLM_TOKEN_COUNTING_MODE", _RUNTIME_MODE_HEURISTIC),
        )
        _runtime_mode = _normalize_runtime_mode(configured)
    return _runtime_mode


def get_tiktoken_cache_dir() -> str:
    """获取 tiktoken 缓存目录。"""
    explicit = (
        os.getenv("TIKTOKEN_CACHE_DIR")
        or getattr(settings, "TIKTOKEN_CACHE_DIR", "")
        or os.getenv("DATA_GYM_CACHE_DIR")
        or ""
    )
    return str(explicit).strip()


def ensure_tiktoken_cache_dir() -> Optional[str]:
    """配置并创建 tiktoken 缓存目录。"""
    cache_dir = get_tiktoken_cache_dir()
    if not cache_dir:
        return None

    os.environ.setdefault("TIKTOKEN_CACHE_DIR", cache_dir)
    try:
        os.makedirs(cache_dir, exist_ok=True)
    except OSError as exc:
        logger.warning("创建 tiktoken 缓存目录失败: %s", exc)
    return cache_dir


def _log_method_once(message: str, level: int = logging.INFO) -> None:
    global _logged_method
    if _logged_method:
        return
    _logged_method = True
    logger.log(level, message)


def _load_precise_encoder(model: str):
    """在显式精确模式下加载 tiktoken 编码器。"""
    global _tiktoken_available

    if model in _encoders:
        return _encoders[model]

    ensure_tiktoken_cache_dir()

    try:
        import tiktoken

        try:
            encoder = tiktoken.encoding_for_model(model)
        except KeyError:
            encoder = tiktoken.get_encoding("cl100k_base")

        _encoders[model] = encoder
        _tiktoken_available = True
        return encoder
    except ImportError:
        _tiktoken_available = False
        logger.debug("tiktoken not installed, falling back to heuristic estimation")
        return None
    except Exception as exc:
        _tiktoken_available = False
        logger.warning("Failed to initialize precise tiktoken encoder for %s: %s", model, exc)
        return None


def _get_tiktoken_encoder(model: str):
    """根据运行时模式获取 tiktoken 编码器。"""
    mode = get_runtime_token_counting_mode()

    if mode == _RUNTIME_MODE_HEURISTIC:
        return None

    if model in _encoders:
        return _encoders[model]

    if mode == _RUNTIME_MODE_AUTO:
        logger.debug(
            "Token counting mode=auto but encoder %s is not prewarmed; using heuristic fallback",
            model,
        )
        return None

    return _load_precise_encoder(model)


class TokenEstimator:
    """Token 估算器。"""

    @staticmethod
    def count_tokens(text: str, model: str = "gpt-4") -> int:
        """计算文本 token 数量。"""
        if not text:
            return 0

        mode = get_runtime_token_counting_mode()
        if mode == _RUNTIME_MODE_HEURISTIC:
            _log_method_once("⚡ Token 计数方案: 启发式估算（默认无网络依赖）")
            return TokenEstimator._heuristic_estimate(text)

        encoder = _get_tiktoken_encoder(model)
        if encoder is not None:
            try:
                count = len(encoder.encode(text))
                strategy = "预热 tiktoken 精确计数" if mode == _RUNTIME_MODE_AUTO else "tiktoken 精确计数"
                _log_method_once(f"Token 计数方案: {strategy}")
                return count
            except Exception as exc:
                logger.debug("tiktoken encode failed: %s, falling back to heuristic", exc)

        if mode == _RUNTIME_MODE_PRECISE:
            _log_method_once(
                "Token 计数方案: 启发式估算（精确计数不可用，已回退）",
                level=logging.WARNING,
            )
        elif mode == _RUNTIME_MODE_AUTO:
            _log_method_once("⚡ Token 计数方案: 启发式估算（auto 模式未命中预热缓存）")
        else:
            _log_method_once("⚡ Token 计数方案: 启发式估算")

        return TokenEstimator._heuristic_estimate(text)

    @staticmethod
    def fast_count_tokens(text: str, model: str = "gpt-4") -> int:
        """始终使用启发式估算。"""
        if not text:
            return 0
        return TokenEstimator._heuristic_estimate(text)

    @staticmethod
    def _heuristic_estimate(text: str) -> int:
        """启发式 token 估算。"""
        if not text:
            return 0

        ascii_chars = 0
        cjk_chars = 0
        other_chars = 0

        for char in text:
            code = ord(char)
            if code < 128:
                ascii_chars += 1
            elif 0x4E00 <= code <= 0x9FFF:
                cjk_chars += 1
            elif 0x3400 <= code <= 0x4DBF:
                cjk_chars += 1
            elif 0x20000 <= code <= 0x2A6DF:
                cjk_chars += 1
            elif 0x3000 <= code <= 0x303F:
                cjk_chars += 1
            elif 0xFF00 <= code <= 0xFFEF:
                cjk_chars += 1
            else:
                other_chars += 1

        tokens = (
            ascii_chars / 4.0
            + cjk_chars / 1.5
            + other_chars / 2.0
        )
        return max(1, int(tokens + 0.5))

    @staticmethod
    def estimate_messages_tokens(messages: list, model: str = "gpt-4") -> int:
        """估算消息列表的 token 数量。"""
        total = 0

        for msg in messages:
            total += 4

            content = msg.get("content", "")
            if isinstance(content, str):
                total += TokenEstimator.count_tokens(content, model)
            elif isinstance(content, list):
                for part in content:
                    if isinstance(part, dict) and part.get("type") == "text":
                        total += TokenEstimator.count_tokens(part.get("text", ""), model)

        total += 3
        return total


def prewarm_tiktoken(model: Optional[str] = None) -> bool:
    """可选预热 tiktoken 编码器。失败只记日志，不影响服务。"""
    ensure_tiktoken_cache_dir()

    try:
        import tiktoken

        warmed = 0
        for encoding_name in ("cl100k_base", "o200k_base"):
            try:
                encoder = tiktoken.get_encoding(encoding_name)
                _encoders.setdefault(encoding_name, encoder)
                warmed += 1
            except Exception as exc:
                logger.debug("预热 tiktoken 编码 %s 失败: %s", encoding_name, exc)

        if model:
            try:
                encoder = tiktoken.encoding_for_model(model)
            except KeyError:
                encoder = tiktoken.get_encoding("cl100k_base")
            _encoders[model] = encoder
            warmed += 1

        if warmed:
            logger.info("tiktoken 预热完成: warmed=%s, cache_dir=%s", warmed, get_tiktoken_cache_dir() or "<default>")
            return True

        logger.warning("tiktoken 预热未命中任何编码器")
        return False
    except ImportError:
        logger.warning("跳过 tiktoken 预热：tiktoken 未安装")
        return False
    except Exception as exc:
        logger.warning("tiktoken 预热失败，继续使用启发式估算: %s", exc)
        return False


# 在模块加载时只配置缓存目录，不做网络相关动作。
ensure_tiktoken_cache_dir()
