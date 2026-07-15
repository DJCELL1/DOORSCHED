import hashlib
from datetime import date

import db

JOB_COLOR_PALETTE = [
    "#4e79a7", "#f28e2b", "#e15759", "#76b7b2", "#59a14f",
    "#edc948", "#b07aa1", "#ff9da7", "#9c755f", "#bab0ac",
    "#86bcb6", "#d37295",
]


def get_holiday_dates():
    return {date.fromisoformat(h["date"]) for h in db.get_holidays()}


def color_for_pro(pro: str) -> str:
    idx = int(hashlib.md5(pro.encode()).hexdigest(), 16) % len(JOB_COLOR_PALETTE)
    return JOB_COLOR_PALETTE[idx]
