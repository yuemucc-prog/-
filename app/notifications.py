from __future__ import annotations

import json
from datetime import timedelta
from typing import Dict, List, Optional, Tuple

import httpx

from .store import Store
from .utils import (
    extract_prefix,
    format_countdown,
    now_local,
    parse_datetime,
    parse_user_time,
    render_template,
    to_iso,
)


def build_message(timer: Dict[str, object], lead_minutes: int) -> Tuple[str, str]:
    next_run_at = str(timer["next_run_at"])
    countdown = format_countdown(int(timer["countdown_seconds"]))
    lead_label = "Boss 已刷新" if lead_minutes == 0 else f"距离刷新还有 {lead_minutes} 分钟"
    context = {
        "timer_name": timer["name"],
        "lead_minutes": lead_minutes,
        "lead_label": lead_label,
        "next_run_local": next_run_at,
        "countdown": countdown,
        "note": timer.get("note", ""),
    }
    template = str(timer.get("message_template") or "[{timer_name}] {lead_label}，下次刷新：{next_run_local}")
    content = render_template(template, context)
    title = f"{timer['name']} · {'刷新' if lead_minutes == 0 else '预提醒'}"
    return title, content


async def send_integration_message(
    integration: Dict[str, object],
    timer: Dict[str, object],
    lead_minutes: int,
) -> Tuple[bool, str]:
    _, content = build_message(timer, lead_minutes)
    headers = {"Content-Type": "application/json"}
    headers.update({str(key): str(value) for key, value in dict(integration.get("headers", {})).items()})
    webhook_url = str(integration.get("webhook_url") or "").strip()
    if not webhook_url:
        return False, "未配置 webhook_url"
    if integration["type"] == "wecom_group_bot":
        payload = {
            "msgtype": "markdown",
            "markdown": {"content": content},
        }
    else:
        body_template = str(integration.get("body_template") or "").strip()
        if body_template:
            rendered = render_template(
                body_template,
                {
                    "timer_name": timer["name"],
                    "lead_minutes": lead_minutes,
                    "next_run_local": timer["next_run_at"],
                    "content": content,
                },
            )
            try:
                payload = json.loads(rendered)
            except json.JSONDecodeError:
                payload = {"content": rendered}
        else:
            payload = {"content": content}
    async with httpx.AsyncClient(timeout=10.0, trust_env=False) as client:
        response = await client.post(webhook_url, headers=headers, json=payload)
        response.raise_for_status()
    return True, f"HTTP {response.status_code}"


def command_help(prefix: str) -> str:
    actual = prefix or "boss"
    return "\n".join(
        [
            f"{actual} 帮助",
            f"{actual} 列表",
            f"{actual} 重置 默认 Boss",
            f"{actual} 延后 默认 Boss 5",
            f"{actual} 下次 默认 Boss 21:30",
            f"{actual} 间隔 默认 Boss 31",
            f"{actual} 提醒 默认 Boss 10,5,1,0",
            f"{actual} 开启 默认 Boss",
            f"{actual} 关闭 默认 Boss",
        ]
    )


def _resolve_timer(store: Store, maybe_name: Optional[str]) -> Dict[str, object]:
    timers = store.list_timers()
    if maybe_name:
        timer = store.find_timer_by_name(maybe_name)
        if timer:
            return timer
        raise ValueError(f"找不到计时器：{maybe_name}")
    if len(timers) == 1:
        return timers[0]
    raise ValueError("存在多个计时器，请带上名称。")


def _parse_named_value(parts: List[str]) -> Tuple[Optional[str], str]:
    if len(parts) == 1:
        return None, parts[0]
    return " ".join(parts[:-1]), parts[-1]


def execute_command(store: Store, integration: Dict[str, object], text: str) -> str:
    prefix = str(integration.get("command_prefix") or "boss")
    body = extract_prefix(text, prefix)
    lowered = body.lower().strip()

    if lowered in {"帮助", "help", "h", "?"}:
        return command_help(prefix)
    if lowered in {"列表", "list", "ls"}:
        timers = store.list_timers()
        lines = []
        for timer in timers:
            status = "运行中" if timer["enabled"] else "已暂停"
            lines.append(f"{timer['name']} | {status} | 下次：{timer['next_run_at']} | 间隔：{timer['interval_minutes']} 分钟")
        return "\n".join(lines) if lines else "当前还没有计时器。"

    if lowered.startswith(("重置", "reset")):
        name = body.split(maxsplit=1)[1] if len(body.split(maxsplit=1)) > 1 else None
        timer = _resolve_timer(store, name)
        updated = store.reset_timer(str(timer["id"]))
        return f"已重置 {updated['name']}，下次刷新：{updated['next_run_at']}"

    if lowered.startswith(("开启", "enable", "关闭", "disable")):
        tokens = body.split(maxsplit=1)
        if len(tokens) < 2:
            raise ValueError("请带上计时器名称。")
        enabled = lowered.startswith(("开启", "enable"))
        timer = _resolve_timer(store, tokens[1])
        updated = store.toggle_timer(str(timer["id"]), enabled)
        return f"{updated['name']} 已{'开启' if enabled else '关闭'}。"

    if lowered.startswith(("延后", "delay")):
        remainder = body.split(maxsplit=1)[1] if len(body.split(maxsplit=1)) > 1 else ""
        parts = remainder.split()
        if not parts:
            raise ValueError("格式应为：延后 计时器名 5")
        maybe_name, raw_minutes = _parse_named_value(parts)
        timer = _resolve_timer(store, maybe_name)
        updated = store.shift_timer(str(timer["id"]), int(raw_minutes))
        return f"{updated['name']} 已延后 {int(raw_minutes)} 分钟，下次刷新：{updated['next_run_at']}"

    if lowered.startswith(("间隔", "interval")):
        remainder = body.split(maxsplit=1)[1] if len(body.split(maxsplit=1)) > 1 else ""
        parts = remainder.split()
        if not parts:
            raise ValueError("格式应为：间隔 计时器名 31")
        maybe_name, raw_interval = _parse_named_value(parts)
        timer = _resolve_timer(store, maybe_name)
        payload = {
            "name": timer["name"],
            "interval_minutes": int(raw_interval),
            "lead_minutes": timer["lead_minutes"],
            "anchor_time": timer["anchor_time"],
            "enabled": timer["enabled"],
            "color": timer["color"],
            "note": timer["note"],
            "message_template": timer["message_template"],
            "integration_ids": timer["integration_ids"],
        }
        updated = store.update_timer(str(timer["id"]), payload)
        return f"{updated['name']} 的循环已改为 {raw_interval} 分钟，下次刷新：{updated['next_run_at']}"

    if lowered.startswith(("提醒", "leads")):
        remainder = body.split(maxsplit=1)[1] if len(body.split(maxsplit=1)) > 1 else ""
        parts = remainder.split()
        if not parts:
            raise ValueError("格式应为：提醒 计时器名 10,5,1,0")
        maybe_name, raw_leads = _parse_named_value(parts)
        timer = _resolve_timer(store, maybe_name)
        lead_values = [int(part.strip()) for part in raw_leads.replace("，", ",").split(",") if part.strip()]
        payload = {
            "name": timer["name"],
            "interval_minutes": timer["interval_minutes"],
            "lead_minutes": lead_values,
            "anchor_time": timer["anchor_time"],
            "enabled": timer["enabled"],
            "color": timer["color"],
            "note": timer["note"],
            "message_template": timer["message_template"],
            "integration_ids": timer["integration_ids"],
        }
        updated = store.update_timer(str(timer["id"]), payload)
        return f"{updated['name']} 的提醒点已改为 {','.join(str(item) for item in updated['lead_minutes'])}"

    if lowered.startswith(("下次", "next")):
        remainder = body.split(maxsplit=1)[1] if len(body.split(maxsplit=1)) > 1 else ""
        parts = remainder.split()
        if not parts:
            raise ValueError("格式应为：下次 计时器名 21:30")
        maybe_name, raw_time = _parse_named_value(parts)
        timer = _resolve_timer(store, maybe_name)
        target = parse_user_time(raw_time)
        updated = store.set_next_run(str(timer["id"]), target)
        return f"{updated['name']} 的下次刷新已改为 {updated['next_run_at']}"

    raise ValueError("无法识别命令，发送“帮助”查看支持的格式。")


async def advance_due_notifications(store: Store) -> List[Dict[str, object]]:
    results: List[Dict[str, object]] = []
    settings = store.get_settings()
    grace_seconds = int(settings.get("scheduler_grace_seconds", "75"))
    now = now_local()

    for timer in store.list_timers():
        if not timer["enabled"]:
            continue
        next_run_dt = parse_datetime(timer["next_run_at"])
        assert next_run_dt is not None
        interval = int(timer["interval_minutes"])
        updated_next = next_run_dt
        advanced = False
        while updated_next <= now:
            delta_seconds = int((now - updated_next).total_seconds())
            if delta_seconds <= grace_seconds:
                results.extend(await _dispatch_notifications(store, timer, updated_next, 0))
            updated_next = updated_next + timedelta(minutes=interval)
            advanced = True
        if advanced:
            store.reconcile_next_run(str(timer["id"]), to_iso(updated_next))
            timer = store.get_timer(str(timer["id"]))
            next_run_dt = parse_datetime(timer["next_run_at"])
            assert next_run_dt is not None
        for lead in timer["lead_minutes"]:
            if lead == 0:
                continue
            due_at = next_run_dt - timedelta(minutes=int(lead))
            if due_at <= now and (now - due_at).total_seconds() <= grace_seconds:
                results.extend(await _dispatch_notifications(store, timer, next_run_dt, int(lead)))
    return results


async def _dispatch_notifications(
    store: Store,
    timer: Dict[str, object],
    cycle_run_at,
    lead_minutes: int,
) -> List[Dict[str, object]]:
    targets = store.integrations_for_timer(str(timer["id"]))
    if not targets:
        event_key = f"{timer['id']}:{to_iso(cycle_run_at)}:{lead_minutes}:no_target"
        if not store.event_exists(event_key):
            store.log_event(
                event_type="notification_skipped",
                title=f"{timer['name']} 未发送提醒",
                body="当前没有可用的默认机器人或绑定通道。",
                timer_id=str(timer["id"]),
                status="warning",
                event_key=event_key,
            )
        return []

    outcomes: List[Dict[str, object]] = []
    timer_for_message = dict(timer)
    timer_for_message["next_run_at"] = to_iso(cycle_run_at)
    timer_for_message["countdown_seconds"] = max(0, int((cycle_run_at - now_local()).total_seconds()))

    for integration in targets:
        event_key = f"{timer['id']}:{to_iso(cycle_run_at)}:{lead_minutes}:{integration['id']}"
        if store.event_exists(event_key):
            continue
        try:
            ok, detail = await send_integration_message(integration, timer_for_message, lead_minutes)
            status = "success" if ok else "error"
            body = build_message(timer_for_message, lead_minutes)[1]
            event = store.log_event(
                event_type="notification_sent" if ok else "notification_failed",
                title=f"{timer['name']} -> {integration['name']}",
                body=body,
                detail=detail,
                status=status,
                timer_id=str(timer["id"]),
                integration_id=str(integration["id"]),
                event_key=event_key,
            )
            outcomes.append(event)
        except Exception as exc:  # noqa: BLE001
            event = store.log_event(
                event_type="notification_failed",
                title=f"{timer['name']} -> {integration['name']}",
                body=str(exc),
                detail=repr(exc),
                status="error",
                timer_id=str(timer["id"]),
                integration_id=str(integration["id"]),
                event_key=event_key,
            )
            outcomes.append(event)
    return outcomes
