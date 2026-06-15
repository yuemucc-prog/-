from __future__ import annotations

import json
import sqlite3
import threading
from datetime import timedelta
from pathlib import Path
from typing import Dict, Iterable, List, Optional

from .utils import (
    clamp_progress,
    compute_cycle_start,
    compute_next_run,
    countdown_seconds,
    csv_to_leads,
    format_countdown,
    leads_to_csv,
    make_id,
    now_local,
    parse_datetime,
    to_iso,
)


class Store:
    def __init__(self, db_path: Path) -> None:
        self.db_path = db_path
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._write_lock = threading.RLock()
        self._bootstrap()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path, check_same_thread=False)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        conn.execute("PRAGMA journal_mode = WAL")
        return conn

    def _bootstrap(self) -> None:
        with self._connect() as conn:
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS timers (
                  id TEXT PRIMARY KEY,
                  name TEXT NOT NULL,
                  interval_minutes INTEGER NOT NULL,
                  lead_minutes TEXT NOT NULL,
                  anchor_time TEXT NOT NULL,
                  next_run_at TEXT NOT NULL,
                  enabled INTEGER NOT NULL DEFAULT 1,
                  color TEXT NOT NULL DEFAULT '#ff6b57',
                  note TEXT NOT NULL DEFAULT '',
                  message_template TEXT NOT NULL DEFAULT '',
                  created_at TEXT NOT NULL,
                  updated_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS integrations (
                  id TEXT PRIMARY KEY,
                  name TEXT NOT NULL,
                  type TEXT NOT NULL,
                  enabled INTEGER NOT NULL DEFAULT 1,
                  is_default INTEGER NOT NULL DEFAULT 0,
                  webhook_url TEXT NOT NULL DEFAULT '',
                  headers_json TEXT NOT NULL DEFAULT '{}',
                  body_template TEXT NOT NULL DEFAULT '',
                  command_enabled INTEGER NOT NULL DEFAULT 0,
                  command_token TEXT NOT NULL DEFAULT '',
                  command_prefix TEXT NOT NULL DEFAULT 'boss',
                  created_at TEXT NOT NULL,
                  updated_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS timer_targets (
                  timer_id TEXT NOT NULL,
                  integration_id TEXT NOT NULL,
                  PRIMARY KEY (timer_id, integration_id),
                  FOREIGN KEY(timer_id) REFERENCES timers(id) ON DELETE CASCADE,
                  FOREIGN KEY(integration_id) REFERENCES integrations(id) ON DELETE CASCADE
                );

                CREATE TABLE IF NOT EXISTS events (
                  id TEXT PRIMARY KEY,
                  event_key TEXT UNIQUE,
                  timer_id TEXT,
                  integration_id TEXT,
                  event_type TEXT NOT NULL,
                  title TEXT NOT NULL,
                  body TEXT NOT NULL DEFAULT '',
                  status TEXT NOT NULL DEFAULT 'info',
                  detail TEXT NOT NULL DEFAULT '',
                  created_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS settings (
                  key TEXT PRIMARY KEY,
                  value TEXT NOT NULL
                );
                """
            )
        self._seed()

    def _seed(self) -> None:
        now = now_local()
        with self._connect() as conn:
            timer_count = conn.execute("SELECT COUNT(*) AS total FROM timers").fetchone()["total"]
            if timer_count == 0:
                timer_id = make_id("timer")
                anchor_time = now
                next_run_at = compute_next_run(anchor_time, 31, now)
                conn.execute(
                    """
                    INSERT INTO timers (
                      id, name, interval_minutes, lead_minutes, anchor_time, next_run_at,
                      enabled, color, note, message_template, created_at, updated_at
                    ) VALUES (?, ?, ?, ?, ?, ?, 1, ?, ?, ?, ?, ?)
                    """,
                    (
                        timer_id,
                        "默认 Boss",
                        31,
                        "5,1,0",
                        to_iso(anchor_time),
                        to_iso(next_run_at),
                        "#ff7a59",
                        "",
                        "[{{timer_name}}] {{lead_label}}，下次刷新：{{next_run_local}}",
                        to_iso(now),
                        to_iso(now),
                    ),
                )
            settings_count = conn.execute("SELECT COUNT(*) AS total FROM settings").fetchone()["total"]
            if settings_count == 0:
                defaults = {
                    "site_title": "Boss 循环计时器",
                    "broadcast_hint": "当前数据保存在这台电脑本机。",
                    "scheduler_grace_seconds": "75",
                }
                conn.executemany(
                    "INSERT INTO settings (key, value) VALUES (?, ?)",
                    list(defaults.items()),
                )

    def _row_to_timer(self, row: sqlite3.Row, integration_ids: List[str]) -> Dict[str, object]:
        next_run_at = parse_datetime(row["next_run_at"])
        now = now_local()
        assert next_run_at is not None
        return {
            "id": row["id"],
            "name": row["name"],
            "interval_minutes": row["interval_minutes"],
            "lead_minutes": csv_to_leads(row["lead_minutes"]),
            "anchor_time": row["anchor_time"],
            "next_run_at": row["next_run_at"],
            "enabled": bool(row["enabled"]),
            "color": row["color"],
            "note": row["note"],
            "message_template": row["message_template"],
            "integration_ids": integration_ids,
            "countdown_seconds": countdown_seconds(next_run_at, now),
            "countdown_label": format_countdown(countdown_seconds(next_run_at, now)),
            "progress": clamp_progress(next_run_at, row["interval_minutes"], now),
            "cycle_start": to_iso(compute_cycle_start(next_run_at, row["interval_minutes"])),
            "created_at": row["created_at"],
            "updated_at": row["updated_at"],
        }

    def _timer_target_map(self, conn: sqlite3.Connection) -> Dict[str, List[str]]:
        rows = conn.execute("SELECT timer_id, integration_id FROM timer_targets").fetchall()
        mapping: Dict[str, List[str]] = {}
        for row in rows:
            mapping.setdefault(row["timer_id"], []).append(row["integration_id"])
        return mapping

    def list_timers(self) -> List[Dict[str, object]]:
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT * FROM timers ORDER BY enabled DESC, next_run_at ASC, created_at ASC"
            ).fetchall()
            mapping = self._timer_target_map(conn)
            return [self._row_to_timer(row, mapping.get(row["id"], [])) for row in rows]

    def get_timer(self, timer_id: str) -> Dict[str, object]:
        with self._connect() as conn:
            row = conn.execute("SELECT * FROM timers WHERE id = ?", (timer_id,)).fetchone()
            if row is None:
                raise KeyError("timer_not_found")
            mapping = self._timer_target_map(conn)
            return self._row_to_timer(row, mapping.get(timer_id, []))

    def find_timer_by_name(self, name: str) -> Optional[Dict[str, object]]:
        name = name.strip().lower()
        for timer in self.list_timers():
            candidate = str(timer["name"]).strip().lower()
            if candidate == name or name in candidate:
                return timer
        return None

    def _save_targets(self, conn: sqlite3.Connection, timer_id: str, integration_ids: Iterable[str]) -> None:
        cleaned = list(dict.fromkeys(integration_ids))
        conn.execute("DELETE FROM timer_targets WHERE timer_id = ?", (timer_id,))
        if cleaned:
            conn.executemany(
                "INSERT INTO timer_targets (timer_id, integration_id) VALUES (?, ?)",
                [(timer_id, integration_id) for integration_id in cleaned],
            )

    def create_timer(self, payload: Dict[str, object]) -> Dict[str, object]:
        with self._write_lock, self._connect() as conn:
            now = now_local()
            timer_id = make_id("timer")
            interval_minutes = int(payload["interval_minutes"])
            anchor_time = parse_datetime(str(payload.get("anchor_time") or to_iso(now))) or now
            next_run_at = compute_next_run(anchor_time, interval_minutes, now)
            conn.execute(
                """
                INSERT INTO timers (
                  id, name, interval_minutes, lead_minutes, anchor_time, next_run_at,
                  enabled, color, note, message_template, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    timer_id,
                    payload["name"],
                    interval_minutes,
                    leads_to_csv(payload.get("lead_minutes", [5, 1, 0])),
                    to_iso(anchor_time),
                    to_iso(next_run_at),
                    int(bool(payload.get("enabled", True))),
                    payload.get("color", "#ff7a59"),
                    payload.get("note", ""),
                    payload.get("message_template", ""),
                    to_iso(now),
                    to_iso(now),
                ),
            )
            self._save_targets(conn, timer_id, payload.get("integration_ids", []))
        self.log_event(
            event_type="timer_created",
            title=f"已创建计时器：{payload['name']}",
            body=f"循环 {interval_minutes} 分钟，提醒点 {leads_to_csv(payload.get('lead_minutes', [5, 1, 0]))}",
            timer_id=timer_id,
        )
        return self.get_timer(timer_id)

    def update_timer(self, timer_id: str, payload: Dict[str, object]) -> Dict[str, object]:
        with self._write_lock, self._connect() as conn:
            row = conn.execute("SELECT * FROM timers WHERE id = ?", (timer_id,)).fetchone()
            if row is None:
                raise KeyError("timer_not_found")
            now = now_local()
            interval_minutes = int(payload["interval_minutes"])
            anchor_time = parse_datetime(str(payload.get("anchor_time") or row["anchor_time"])) or now
            next_run_at = compute_next_run(anchor_time, interval_minutes, now)
            conn.execute(
                """
                UPDATE timers
                SET name = ?, interval_minutes = ?, lead_minutes = ?, anchor_time = ?, next_run_at = ?,
                    enabled = ?, color = ?, note = ?, message_template = ?, updated_at = ?
                WHERE id = ?
                """,
                (
                    payload["name"],
                    interval_minutes,
                    leads_to_csv(payload.get("lead_minutes", [5, 1, 0])),
                    to_iso(anchor_time),
                    to_iso(next_run_at),
                    int(bool(payload.get("enabled", True))),
                    payload.get("color", "#ff7a59"),
                    payload.get("note", ""),
                    payload.get("message_template", ""),
                    to_iso(now),
                    timer_id,
                ),
            )
            self._save_targets(conn, timer_id, payload.get("integration_ids", []))
        self.log_event(
            event_type="timer_updated",
            title=f"已更新计时器：{payload['name']}",
            body=f"下次刷新时间自动重算为 {to_iso(next_run_at)}",
            timer_id=timer_id,
        )
        return self.get_timer(timer_id)

    def delete_timer(self, timer_id: str) -> None:
        timer = self.get_timer(timer_id)
        with self._write_lock, self._connect() as conn:
            conn.execute("DELETE FROM timers WHERE id = ?", (timer_id,))
        self.log_event(
            event_type="timer_deleted",
            title=f"已删除计时器：{timer['name']}",
            timer_id=timer_id,
        )

    def shift_timer(self, timer_id: str, minutes: int) -> Dict[str, object]:
        timer = self.get_timer(timer_id)
        next_run_at = parse_datetime(str(timer["next_run_at"]))
        assert next_run_at is not None
        updated_next = next_run_at + timedelta(minutes=minutes)
        return self.set_next_run(timer_id, updated_next)

    def reset_timer(self, timer_id: str, anchor_time: Optional[str] = None) -> Dict[str, object]:
        timer = self.get_timer(timer_id)
        anchor = parse_datetime(anchor_time) if anchor_time else now_local()
        assert anchor is not None
        next_run_at = compute_next_run(anchor, int(timer["interval_minutes"]), anchor)
        with self._write_lock, self._connect() as conn:
            conn.execute(
                "UPDATE timers SET anchor_time = ?, next_run_at = ?, updated_at = ? WHERE id = ?",
                (to_iso(anchor), to_iso(next_run_at), to_iso(now_local()), timer_id),
            )
        self.log_event(
            event_type="timer_reset",
            title=f"已校准：{timer['name']}",
            body=f"新的下一次刷新：{to_iso(next_run_at)}",
            timer_id=timer_id,
        )
        return self.get_timer(timer_id)

    def set_next_run(self, timer_id: str, next_run_at) -> Dict[str, object]:
        timer = self.get_timer(timer_id)
        target = parse_datetime(str(next_run_at)) if not hasattr(next_run_at, "tzinfo") else next_run_at
        assert target is not None
        interval_minutes = int(timer["interval_minutes"])
        anchor = target - timedelta(minutes=interval_minutes)
        with self._write_lock, self._connect() as conn:
            conn.execute(
                "UPDATE timers SET anchor_time = ?, next_run_at = ?, updated_at = ? WHERE id = ?",
                (to_iso(anchor), to_iso(target), to_iso(now_local()), timer_id),
            )
        self.log_event(
            event_type="timer_next_run",
            title=f"已修改下次刷新：{timer['name']}",
            body=f"新的下次刷新时间：{to_iso(target)}",
            timer_id=timer_id,
        )
        return self.get_timer(timer_id)

    def toggle_timer(self, timer_id: str, enabled: bool) -> Dict[str, object]:
        timer = self.get_timer(timer_id)
        with self._write_lock, self._connect() as conn:
            conn.execute(
                "UPDATE timers SET enabled = ?, updated_at = ? WHERE id = ?",
                (int(enabled), to_iso(now_local()), timer_id),
            )
        self.log_event(
            event_type="timer_toggled",
            title=f"{'启用' if enabled else '暂停'}计时器：{timer['name']}",
            timer_id=timer_id,
        )
        return self.get_timer(timer_id)

    def reconcile_next_run(self, timer_id: str, next_run_at: str) -> None:
        with self._write_lock, self._connect() as conn:
            conn.execute(
                "UPDATE timers SET next_run_at = ?, updated_at = ? WHERE id = ?",
                (next_run_at, to_iso(now_local()), timer_id),
            )

    def list_integrations(self) -> List[Dict[str, object]]:
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT * FROM integrations ORDER BY enabled DESC, is_default DESC, created_at ASC"
            ).fetchall()
            return [self._row_to_integration(row) for row in rows]

    def _row_to_integration(self, row: sqlite3.Row) -> Dict[str, object]:
        return {
            "id": row["id"],
            "name": row["name"],
            "type": row["type"],
            "enabled": bool(row["enabled"]),
            "is_default": bool(row["is_default"]),
            "webhook_url": row["webhook_url"],
            "headers": json.loads(row["headers_json"] or "{}"),
            "body_template": row["body_template"],
            "command_enabled": bool(row["command_enabled"]),
            "command_token": row["command_token"],
            "command_prefix": row["command_prefix"],
            "created_at": row["created_at"],
            "updated_at": row["updated_at"],
        }

    def create_integration(self, payload: Dict[str, object]) -> Dict[str, object]:
        with self._write_lock, self._connect() as conn:
            now = now_local()
            integration_id = make_id("bot")
            conn.execute(
                """
                INSERT INTO integrations (
                  id, name, type, enabled, is_default, webhook_url, headers_json, body_template,
                  command_enabled, command_token, command_prefix, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    integration_id,
                    payload["name"],
                    payload["type"],
                    int(bool(payload.get("enabled", True))),
                    int(bool(payload.get("is_default", False))),
                    payload.get("webhook_url", ""),
                    json.dumps(payload.get("headers", {}), ensure_ascii=False),
                    payload.get("body_template", ""),
                    int(bool(payload.get("command_enabled", False))),
                    payload.get("command_token", ""),
                    payload.get("command_prefix", "boss"),
                    to_iso(now),
                    to_iso(now),
                ),
            )
            if payload.get("is_default"):
                conn.execute(
                    "UPDATE integrations SET is_default = 0 WHERE id != ?",
                    (integration_id,),
                )
        self.log_event(
            event_type="integration_created",
            title=f"已创建机器人通道：{payload['name']}",
            integration_id=integration_id,
        )
        return self.get_integration(integration_id)

    def update_integration(self, integration_id: str, payload: Dict[str, object]) -> Dict[str, object]:
        with self._write_lock, self._connect() as conn:
            row = conn.execute("SELECT * FROM integrations WHERE id = ?", (integration_id,)).fetchone()
            if row is None:
                raise KeyError("integration_not_found")
            conn.execute(
                """
                UPDATE integrations
                SET name = ?, type = ?, enabled = ?, is_default = ?, webhook_url = ?, headers_json = ?,
                    body_template = ?, command_enabled = ?, command_token = ?, command_prefix = ?, updated_at = ?
                WHERE id = ?
                """,
                (
                    payload["name"],
                    payload["type"],
                    int(bool(payload.get("enabled", True))),
                    int(bool(payload.get("is_default", False))),
                    payload.get("webhook_url", ""),
                    json.dumps(payload.get("headers", {}), ensure_ascii=False),
                    payload.get("body_template", ""),
                    int(bool(payload.get("command_enabled", False))),
                    payload.get("command_token", ""),
                    payload.get("command_prefix", "boss"),
                    to_iso(now_local()),
                    integration_id,
                ),
            )
            if payload.get("is_default"):
                conn.execute(
                    "UPDATE integrations SET is_default = 0 WHERE id != ?",
                    (integration_id,),
                )
        self.log_event(
            event_type="integration_updated",
            title=f"已更新机器人通道：{payload['name']}",
            integration_id=integration_id,
        )
        return self.get_integration(integration_id)

    def get_integration(self, integration_id: str) -> Dict[str, object]:
        with self._connect() as conn:
            row = conn.execute("SELECT * FROM integrations WHERE id = ?", (integration_id,)).fetchone()
            if row is None:
                raise KeyError("integration_not_found")
            return self._row_to_integration(row)

    def delete_integration(self, integration_id: str) -> None:
        integration = self.get_integration(integration_id)
        with self._write_lock, self._connect() as conn:
            conn.execute("DELETE FROM integrations WHERE id = ?", (integration_id,))
        self.log_event(
            event_type="integration_deleted",
            title=f"已删除机器人通道：{integration['name']}",
            integration_id=integration_id,
        )

    def integrations_for_timer(self, timer_id: str) -> List[Dict[str, object]]:
        with self._connect() as conn:
            targets = conn.execute(
                """
                SELECT i.*
                FROM integrations i
                INNER JOIN timer_targets t ON t.integration_id = i.id
                WHERE t.timer_id = ? AND i.enabled = 1
                ORDER BY i.is_default DESC, i.created_at ASC
                """,
                (timer_id,),
            ).fetchall()
            if targets:
                return [self._row_to_integration(row) for row in targets]
            defaults = conn.execute(
                "SELECT * FROM integrations WHERE enabled = 1 AND is_default = 1 ORDER BY created_at ASC"
            ).fetchall()
            return [self._row_to_integration(row) for row in defaults]

    def find_command_integration(self, token: str) -> Optional[Dict[str, object]]:
        if not token:
            return None
        with self._connect() as conn:
            row = conn.execute(
                """
                SELECT *
                FROM integrations
                WHERE command_enabled = 1 AND command_token = ? AND enabled = 1
                ORDER BY updated_at DESC
                LIMIT 1
                """,
                (token,),
            ).fetchone()
            return self._row_to_integration(row) if row else None

    def event_exists(self, event_key: str) -> bool:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT id FROM events WHERE event_key = ? LIMIT 1",
                (event_key,),
            ).fetchone()
            return row is not None

    def log_event(
        self,
        event_type: str,
        title: str,
        body: str = "",
        *,
        status: str = "info",
        detail: str = "",
        timer_id: Optional[str] = None,
        integration_id: Optional[str] = None,
        event_key: Optional[str] = None,
    ) -> Dict[str, object]:
        event = {
            "id": make_id("evt"),
            "event_key": event_key,
            "timer_id": timer_id,
            "integration_id": integration_id,
            "event_type": event_type,
            "title": title,
            "body": body,
            "status": status,
            "detail": detail,
            "created_at": to_iso(now_local()),
        }
        with self._write_lock, self._connect() as conn:
            conn.execute(
                """
                INSERT OR IGNORE INTO events (
                  id, event_key, timer_id, integration_id, event_type,
                  title, body, status, detail, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    event["id"],
                    event["event_key"],
                    event["timer_id"],
                    event["integration_id"],
                    event["event_type"],
                    event["title"],
                    event["body"],
                    event["status"],
                    event["detail"],
                    event["created_at"],
                ),
            )
        return event

    def list_events(self, limit: int = 60) -> List[Dict[str, object]]:
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT * FROM events ORDER BY created_at DESC LIMIT ?",
                (limit,),
            ).fetchall()
            return [dict(row) for row in rows]

    def get_settings(self) -> Dict[str, str]:
        with self._connect() as conn:
            rows = conn.execute("SELECT key, value FROM settings").fetchall()
            return {row["key"]: row["value"] for row in rows}

    def update_settings(self, payload: Dict[str, str]) -> Dict[str, str]:
        with self._write_lock, self._connect() as conn:
            conn.executemany(
                """
                INSERT INTO settings (key, value)
                VALUES (?, ?)
                ON CONFLICT(key) DO UPDATE SET value = excluded.value
                """,
                list(payload.items()),
            )
        self.log_event(
            event_type="settings_updated",
            title="已更新全局设置",
            body=", ".join(f"{key}={value}" for key, value in payload.items()),
        )
        return self.get_settings()

    def snapshot(self) -> Dict[str, object]:
        return {
            "timers": self.list_timers(),
            "integrations": self.list_integrations(),
            "events": self.list_events(80),
            "settings": self.get_settings(),
            "server_time": to_iso(now_local()),
        }
