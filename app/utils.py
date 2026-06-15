from __future__ import annotations

import re
import uuid
from datetime import datetime, timedelta
from typing import Dict, Iterable, List, Optional
from zoneinfo import ZoneInfo

LOCAL_ZONE = datetime.now().astimezone().tzinfo or ZoneInfo("Asia/Shanghai")


def now_local() -> datetime:
    return datetime.now(tz=LOCAL_ZONE)


def parse_datetime(value: Optional[str]) -> Optional[datetime]:
    if not value:
        return None
    normalized = value.strip().replace("Z", "+00:00")
    parsed = datetime.fromisoformat(normalized)
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=LOCAL_ZONE)
    return parsed.astimezone(LOCAL_ZONE)


def to_iso(dt: datetime) -> str:
    normalized = dt.astimezone(LOCAL_ZONE).replace(microsecond=0)
    return normalized.isoformat()


def normalize_leads(values: Iterable[int]) -> List[int]:
    unique = {max(0, int(value)) for value in values}
    if 0 not in unique:
        unique.add(0)
    return sorted(unique, reverse=True)


def leads_to_csv(values: Iterable[int]) -> str:
    return ",".join(str(item) for item in normalize_leads(values))


def csv_to_leads(value: str) -> List[int]:
    pieces = [part.strip() for part in (value or "").replace("，", ",").split(",")]
    cleaned = [int(part) for part in pieces if part]
    return normalize_leads(cleaned or [5, 1, 0])


def compute_next_run(anchor_time: datetime, interval_minutes: int, now: Optional[datetime] = None) -> datetime:
    current = now or now_local()
    step = timedelta(minutes=interval_minutes)
    next_run = anchor_time + step
    while next_run <= current:
        next_run += step
    return next_run


def compute_cycle_start(next_run_at: datetime, interval_minutes: int) -> datetime:
    return next_run_at - timedelta(minutes=interval_minutes)


def countdown_seconds(next_run_at: datetime, now: Optional[datetime] = None) -> int:
    current = now or now_local()
    return max(0, int((next_run_at - current).total_seconds()))


def format_countdown(seconds: int) -> str:
    hours, remainder = divmod(max(0, seconds), 3600)
    minutes, secs = divmod(remainder, 60)
    return f"{hours:02d}:{minutes:02d}:{secs:02d}"


def clamp_progress(next_run_at: datetime, interval_minutes: int, now: Optional[datetime] = None) -> float:
    current = now or now_local()
    cycle_start = compute_cycle_start(next_run_at, interval_minutes)
    total = max(1, interval_minutes * 60)
    elapsed = int((current - cycle_start).total_seconds())
    return max(0.0, min(1.0, elapsed / total))


def make_id(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex[:10]}"


def render_template(template: str, context: Dict[str, object]) -> str:
    rendered = template or ""
    for key, value in context.items():
        rendered = rendered.replace(f"{{{{{key}}}}}", str(value))
        rendered = rendered.replace(f"{{{key}}}", str(value))
    return rendered


def parse_user_time(raw: str, base: Optional[datetime] = None) -> datetime:
    raw = raw.strip()
    pivot = base or now_local()
    for fmt in ("%Y-%m-%d %H:%M", "%Y/%m/%d %H:%M", "%m-%d %H:%M", "%H:%M"):
        try:
            parsed = datetime.strptime(raw, fmt)
        except ValueError:
            continue
        if fmt == "%H:%M":
            candidate = pivot.replace(hour=parsed.hour, minute=parsed.minute, second=0, microsecond=0)
            if candidate <= pivot:
                candidate += timedelta(days=1)
            return candidate
        if fmt == "%m-%d %H:%M":
            candidate = parsed.replace(year=pivot.year, second=0, microsecond=0, tzinfo=LOCAL_ZONE)
            if candidate <= pivot:
                candidate = candidate.replace(year=pivot.year + 1)
            return candidate
        return parsed.replace(second=0, microsecond=0, tzinfo=LOCAL_ZONE)
    raise ValueError("时间格式无效，请使用 HH:MM 或 YYYY-MM-DD HH:MM。")


def extract_prefix(text: str, prefix: str) -> str:
    normalized = text.strip()
    if not prefix:
        return normalized
    pattern = re.compile(rf"^(?:/)?{re.escape(prefix)}[\s:：]+", re.IGNORECASE)
    if pattern.match(normalized):
        return pattern.sub("", normalized, count=1).strip()
    return normalized
