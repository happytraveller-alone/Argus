"""测试日期工具函数"""

from datetime import datetime, timezone, timedelta
import pytest

from app.utils.date_utils import format_iso, format_chinese, relative_time


def test_format_iso():
    """测试 ISO 8601 格式化"""
    dt = datetime(2026, 3, 7, 12, 0, 0, tzinfo=timezone.utc)
    result = format_iso(dt)
    assert result == "2026-03-07T12:00:00+00:00"


def test_format_iso_with_microseconds():
    """测试带微秒的 ISO 格式化"""
    dt = datetime(2026, 3, 7, 12, 0, 0, 123456, tzinfo=timezone.utc)
    result = format_iso(dt)
    assert "2026-03-07T12:00:00.123456" in result


def test_format_chinese():
    """测试中文格式化"""
    dt = datetime(2026, 3, 7, 12, 0, 0)
    result = format_chinese(dt)
    assert result == "2026年03月07日 12:00:00"


def test_format_chinese_different_time():
    """测试不同时间的中文格式化"""
    dt = datetime(2025, 12, 31, 23, 59, 59)
    result = format_chinese(dt)
    assert result == "2025年12月31日 23:59:59"


def test_relative_time_just_now():
    """测试"刚刚"（小于1分钟）"""
    now = datetime(2026, 3, 7, 12, 0, 0, tzinfo=timezone.utc)
    dt = now - timedelta(seconds=30)
    result = relative_time(dt, now)
    assert result == "刚刚"


def test_relative_time_minutes():
    """测试分钟前"""
    now = datetime(2026, 3, 7, 12, 0, 0, tzinfo=timezone.utc)
    dt = now - timedelta(minutes=5)
    result = relative_time(dt, now)
    assert result == "5分钟前"


def test_relative_time_hours():
    """测试小时前"""
    now = datetime(2026, 3, 7, 12, 0, 0, tzinfo=timezone.utc)
    dt = now - timedelta(hours=2)
    result = relative_time(dt, now)
    assert result == "2小时前"


def test_relative_time_days():
    """测试天前"""
    now = datetime(2026, 3, 7, 12, 0, 0, tzinfo=timezone.utc)
    dt = now - timedelta(days=3)
    result = relative_time(dt, now)
    assert result == "3天前"


def test_relative_time_without_now():
    """测试不提供 now 参数（使用当前时间）"""
    # 创建一个过去的时间
    dt = datetime.now(timezone.utc) - timedelta(minutes=10)
    result = relative_time(dt)
    # 应该返回约10分钟前
    assert "分钟前" in result


def test_relative_time_naive_datetime():
    """测试无时区信息的 datetime（应自动添加 UTC）"""
    now = datetime(2026, 3, 7, 12, 0, 0)
    dt = datetime(2026, 3, 7, 10, 0, 0)
    result = relative_time(dt, now)
    assert result == "2小时前"


def test_relative_time_edge_cases():
    """测试边界情况"""
    now = datetime(2026, 3, 7, 12, 0, 0, tzinfo=timezone.utc)

    # 59秒 - 应该是"刚刚"
    dt1 = now - timedelta(seconds=59)
    assert relative_time(dt1, now) == "刚刚"

    # 60秒 - 应该是"1分钟前"
    dt2 = now - timedelta(seconds=60)
    assert relative_time(dt2, now) == "1分钟前"

    # 59分59秒 - 应该是"59分钟前"
    dt3 = now - timedelta(seconds=3599)
    assert relative_time(dt3, now) == "59分钟前"

    # 1小时 - 应该是"1小时前"
    dt4 = now - timedelta(hours=1)
    assert relative_time(dt4, now) == "1小时前"

    # 23小时59分 - 应该是"23小时前"
    dt5 = now - timedelta(hours=23, minutes=59)
    assert relative_time(dt5, now) == "23小时前"

    # 24小时 - 应该是"1天前"
    dt6 = now - timedelta(days=1)
    assert relative_time(dt6, now) == "1天前"
