"""日期时间工具函数

提供统一的日期格式化和相对时间计算功能
"""

from datetime import datetime, timezone
from typing import Optional


def format_iso(dt: datetime) -> str:
    """格式化为 ISO 8601 格式

    Args:
        dt: 要格式化的日期时间对象

    Returns:
        ISO 8601 格式的字符串

    Example:
        >>> dt = datetime(2026, 3, 7, 12, 0, 0, tzinfo=timezone.utc)
        >>> format_iso(dt)
        '2026-03-07T12:00:00+00:00'
    """
    return dt.isoformat()


def format_chinese(dt: datetime) -> str:
    """格式化为中文友好格式

    Args:
        dt: 要格式化的日期时间对象

    Returns:
        中文格式的日期时间字符串

    Example:
        >>> dt = datetime(2026, 3, 7, 12, 0, 0)
        >>> format_chinese(dt)
        '2026年03月07日 12:00:00'
    """
    return dt.strftime("%Y年%m月%d日 %H:%M:%S")


def relative_time(dt: datetime, now: Optional[datetime] = None) -> str:
    """计算相对时间（如"3小时前"）

    Args:
        dt: 要计算的日期时间对象
        now: 参考时间，默认为当前 UTC 时间

    Returns:
        相对时间的中文描述

    Example:
        >>> now = datetime(2026, 3, 7, 12, 0, 0, tzinfo=timezone.utc)
        >>> dt = now - timedelta(hours=2)
        >>> relative_time(dt, now)
        '2小时前'
    """
    if now is None:
        now = datetime.now(timezone.utc)

    # 确保两个时间都有时区信息
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    if now.tzinfo is None:
        now = now.replace(tzinfo=timezone.utc)

    delta = now - dt
    seconds = delta.total_seconds()

    if seconds < 60:
        return "刚刚"
    elif seconds < 3600:
        return f"{int(seconds / 60)}分钟前"
    elif seconds < 86400:
        return f"{int(seconds / 3600)}小时前"
    else:
        return f"{int(seconds / 86400)}天前"
