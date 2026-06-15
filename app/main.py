from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any, AsyncIterator, Dict, List, Optional

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import HTMLResponse, JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel, Field

from .notifications import advance_due_notifications, command_help, execute_command, send_integration_message
from .runtime import db_path, resource_root
from .store import Store
from .utils import normalize_leads, now_local, parse_datetime, parse_user_time, to_iso

BASE_DIR = resource_root()
DB_PATH = db_path()


class EventBus:
    def __init__(self) -> None:
        self._subscribers: set[asyncio.Queue] = set()

    def subscribe(self) -> asyncio.Queue:
        queue: asyncio.Queue = asyncio.Queue()
        self._subscribers.add(queue)
        return queue

    def unsubscribe(self, queue: asyncio.Queue) -> None:
        self._subscribers.discard(queue)

    async def publish(self, event_type: str, payload: Optional[Dict[str, Any]] = None) -> None:
        message = {"type": event_type, "payload": payload or {}, "time": to_iso(now_local())}
        stale: List[asyncio.Queue] = []
        for queue in list(self._subscribers):
            try:
                queue.put_nowait(message)
            except Exception:  # noqa: BLE001
                stale.append(queue)
        for queue in stale:
            self.unsubscribe(queue)


store = Store(DB_PATH)
bus = EventBus()


class TimerPayload(BaseModel):
    name: str = Field(min_length=1, max_length=60)
    interval_minutes: int = Field(ge=1, le=24 * 60)
    lead_minutes: List[int] = Field(default_factory=lambda: [5, 1, 0])
    anchor_time: Optional[str] = None
    enabled: bool = True
    color: str = "#ff7a59"
    note: str = ""
    message_template: str = ""
    integration_ids: List[str] = Field(default_factory=list)


class TogglePayload(BaseModel):
    enabled: bool


class ResetPayload(BaseModel):
    anchor_time: Optional[str] = None


class ShiftPayload(BaseModel):
    minutes: int = Field(ge=-1440, le=1440)


class NextRunPayload(BaseModel):
    next_run_at: str


class IntegrationPayload(BaseModel):
    name: str = Field(min_length=1, max_length=60)
    type: str
    enabled: bool = True
    is_default: bool = False
    webhook_url: str = ""
    headers: Dict[str, str] = Field(default_factory=dict)
    body_template: str = ""
    command_enabled: bool = False
    command_token: str = ""
    command_prefix: str = "boss"


class SettingsPayload(BaseModel):
    site_title: str
    broadcast_hint: str
    scheduler_grace_seconds: int = Field(ge=5, le=600)


class CommandPayload(BaseModel):
    text: str
    token: str
    source: str = "external-bridge"


templates = Jinja2Templates(directory=str(BASE_DIR / "app" / "templates"))


async def scheduler_loop() -> None:
    while True:
        try:
            events = await advance_due_notifications(store)
            if events:
                await bus.publish("events", {"count": len(events)})
        except Exception as exc:  # noqa: BLE001
            store.log_event(
                event_type="scheduler_error",
                title="调度器异常",
                body=str(exc),
                detail=repr(exc),
                status="error",
            )
            await bus.publish("events", {"count": 1})
        await asyncio.sleep(1)


@asynccontextmanager
async def lifespan(_: FastAPI):
    task = asyncio.create_task(scheduler_loop())
    try:
        yield
    finally:
        task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await task


import contextlib  # noqa: E402


app = FastAPI(title="Boss 循环计时器", lifespan=lifespan)
app.mount("/static", StaticFiles(directory=str(BASE_DIR / "app" / "static")), name="static")


def page_context(request: Request) -> Dict[str, Any]:
    return {
        "request": request,
        "settings": store.get_settings(),
        "command_help": command_help("boss"),
        "timer_message_template_placeholder": "[{{timer_name}}] {{lead_label}}，下次刷新：{{next_run_local}}",
        "integration_body_template_placeholder": '{"content":"{{content}}"}',
    }


def normalize_timer_payload(payload: TimerPayload) -> Dict[str, Any]:
    return {
        "name": payload.name.strip(),
        "interval_minutes": payload.interval_minutes,
        "lead_minutes": normalize_leads(payload.lead_minutes),
        "anchor_time": payload.anchor_time,
        "enabled": payload.enabled,
        "color": payload.color,
        "note": payload.note.strip(),
        "message_template": payload.message_template.strip(),
        "integration_ids": payload.integration_ids,
    }


def normalize_integration_payload(payload: IntegrationPayload) -> Dict[str, Any]:
    if payload.type not in {"wecom_group_bot", "generic_webhook"}:
        raise HTTPException(status_code=400, detail="仅支持 wecom_group_bot 或 generic_webhook。")
    return {
        "name": payload.name.strip(),
        "type": payload.type,
        "enabled": payload.enabled,
        "is_default": payload.is_default,
        "webhook_url": payload.webhook_url.strip(),
        "headers": {key.strip(): value for key, value in payload.headers.items() if key.strip()},
        "body_template": payload.body_template.strip(),
        "command_enabled": payload.command_enabled,
        "command_token": payload.command_token.strip(),
        "command_prefix": payload.command_prefix.strip() or "boss",
    }


@app.get("/", response_class=HTMLResponse)
async def index(request: Request) -> HTMLResponse:
    return templates.TemplateResponse(request, "index.html", page_context(request))


@app.get("/bot", response_class=HTMLResponse)
async def bot_debug(request: Request) -> HTMLResponse:
    return templates.TemplateResponse(request, "bot.html", page_context(request))


@app.get("/api/snapshot")
async def snapshot() -> Dict[str, Any]:
    return store.snapshot()


@app.get("/api/stream")
async def stream() -> StreamingResponse:
    queue = bus.subscribe()

    async def event_source() -> AsyncIterator[str]:
        try:
            yield f"data: {JSONResponse({'type': 'hello', 'time': to_iso(now_local())}).body.decode()}\n\n"
            while True:
                message = await queue.get()
                yield f"data: {JSONResponse(message).body.decode()}\n\n"
        finally:
            bus.unsubscribe(queue)

    return StreamingResponse(event_source(), media_type="text/event-stream")


@app.post("/api/timers")
async def create_timer(payload: TimerPayload) -> Dict[str, Any]:
    created = store.create_timer(normalize_timer_payload(payload))
    await bus.publish("timers", {"timer_id": created["id"]})
    return created


@app.put("/api/timers/{timer_id}")
async def update_timer(timer_id: str, payload: TimerPayload) -> Dict[str, Any]:
    try:
        updated = store.update_timer(timer_id, normalize_timer_payload(payload))
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    await bus.publish("timers", {"timer_id": timer_id})
    return updated


@app.delete("/api/timers/{timer_id}")
async def delete_timer(timer_id: str) -> Dict[str, bool]:
    try:
        store.delete_timer(timer_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    await bus.publish("timers", {"timer_id": timer_id})
    return {"ok": True}


@app.post("/api/timers/{timer_id}/toggle")
async def toggle_timer(timer_id: str, payload: TogglePayload) -> Dict[str, Any]:
    try:
        updated = store.toggle_timer(timer_id, payload.enabled)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    await bus.publish("timers", {"timer_id": timer_id})
    return updated


@app.post("/api/timers/{timer_id}/reset")
async def reset_timer(timer_id: str, payload: ResetPayload) -> Dict[str, Any]:
    try:
        updated = store.reset_timer(timer_id, payload.anchor_time)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    await bus.publish("timers", {"timer_id": timer_id})
    return updated


@app.post("/api/timers/{timer_id}/shift")
async def shift_timer(timer_id: str, payload: ShiftPayload) -> Dict[str, Any]:
    try:
        updated = store.shift_timer(timer_id, payload.minutes)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    await bus.publish("timers", {"timer_id": timer_id})
    return updated


@app.post("/api/timers/{timer_id}/next-run")
async def set_next_run(timer_id: str, payload: NextRunPayload) -> Dict[str, Any]:
    try:
        target = parse_datetime(payload.next_run_at) or parse_user_time(payload.next_run_at)
        updated = store.set_next_run(timer_id, target)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    await bus.publish("timers", {"timer_id": timer_id})
    return updated


@app.post("/api/integrations")
async def create_integration(payload: IntegrationPayload) -> Dict[str, Any]:
    created = store.create_integration(normalize_integration_payload(payload))
    await bus.publish("integrations", {"integration_id": created["id"]})
    return created


@app.put("/api/integrations/{integration_id}")
async def update_integration(integration_id: str, payload: IntegrationPayload) -> Dict[str, Any]:
    try:
        updated = store.update_integration(integration_id, normalize_integration_payload(payload))
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    await bus.publish("integrations", {"integration_id": integration_id})
    return updated


@app.delete("/api/integrations/{integration_id}")
async def delete_integration(integration_id: str) -> Dict[str, bool]:
    try:
        store.delete_integration(integration_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    await bus.publish("integrations", {"integration_id": integration_id})
    return {"ok": True}


@app.post("/api/integrations/{integration_id}/test")
async def test_integration(integration_id: str) -> Dict[str, Any]:
    try:
        integration = store.get_integration(integration_id)
        timers = store.list_timers()
        timer = timers[0]
    except (KeyError, IndexError) as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    try:
        ok, detail = await send_integration_message(integration, timer, 1)
    except Exception as exc:  # noqa: BLE001
        ok = False
        detail = str(exc)
    store.log_event(
        event_type="integration_test",
        title=f"测试发送：{integration['name']}",
        body=detail,
        status="success" if ok else "error",
        integration_id=integration_id,
        timer_id=str(timer["id"]),
    )
    await bus.publish("events", {"integration_id": integration_id})
    return {"ok": ok, "detail": detail}


@app.post("/api/settings")
async def update_settings(payload: SettingsPayload) -> Dict[str, str]:
    settings = store.update_settings(
        {
            "site_title": payload.site_title.strip(),
            "broadcast_hint": payload.broadcast_hint.strip(),
            "scheduler_grace_seconds": str(payload.scheduler_grace_seconds),
        }
    )
    await bus.publish("settings")
    return settings


@app.post("/api/commands")
async def inbound_command(payload: CommandPayload) -> Dict[str, Any]:
    integration = store.find_command_integration(payload.token.strip())
    if integration is None:
        raise HTTPException(status_code=401, detail="命令 token 无效。")
    try:
        reply = execute_command(store, integration, payload.text)
        store.log_event(
            event_type="command_received",
            title=f"收到机器人命令：{integration['name']}",
            body=payload.text,
            detail=reply,
            integration_id=str(integration["id"]),
            status="success",
        )
    except ValueError as exc:
        reply = str(exc)
        store.log_event(
            event_type="command_rejected",
            title=f"机器人命令执行失败：{integration['name']}",
            body=payload.text,
            detail=reply,
            integration_id=str(integration["id"]),
            status="warning",
        )
    await bus.publish("events", {"integration_id": integration["id"]})
    await bus.publish("timers")
    return {"ok": True, "reply": reply, "source": payload.source}
