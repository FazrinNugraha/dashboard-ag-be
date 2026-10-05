"""Sumber waktu tunggal untuk aplikasi (zona waktu Asia/Jakarta).

Semua penentuan tanggal/hari (tanggal pembayaran, ID PAY/OUT, bulan_filter,
generated_at) harus lewat sini agar konsisten meski server berjalan di UTC.
"""
from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from functools import lru_cache

from app.core.config import get_settings


@lru_cache
def _tz():
    name = get_settings().TIMEZONE
    try:
        from zoneinfo import ZoneInfo

        return ZoneInfo(name)
    except Exception:
        # Windows tanpa data tzdata: fallback ke offset tetap +07:00.
        return timezone(timedelta(hours=7), name)


def now_local() -> datetime:
    """Waktu sekarang di zona aplikasi (timezone-aware)."""
    return datetime.now(_tz())


def today_local() -> date:
    """Tanggal hari ini di zona aplikasi."""
    return now_local().date()