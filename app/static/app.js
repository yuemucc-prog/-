const state = {
  snapshot: null,
  selectedTimerId: null,
  selectedIntegrationId: null,
  serverTime: null,
  snapshotFetchedAt: null,
  refreshTimer: null,
  eventSource: null,
  page: document.body.dataset.page || "dashboard",
};

const els = {};

document.addEventListener("DOMContentLoaded", () => {
  collectElements();
  bindEvents();
  bootstrap();
});

function collectElements() {
  Object.assign(els, {
    siteTitle: document.getElementById("siteTitle"),
    serverTime: document.getElementById("serverTime"),
    liveState: document.getElementById("liveState"),
    exportSnapshotBtn: document.getElementById("exportSnapshotBtn"),
    heroName: document.getElementById("heroName"),
    heroCountdown: document.getElementById("heroCountdown"),
    heroProgressBar: document.getElementById("heroProgressBar"),
    heroNextRun: document.getElementById("heroNextRun"),
    heroInterval: document.getElementById("heroInterval"),
    heroLeads: document.getElementById("heroLeads"),
    heroNextRunInput: document.getElementById("heroNextRunInput"),
    heroResetBtn: document.getElementById("heroResetBtn"),
    heroApplyNextRunBtn: document.getElementById("heroApplyNextRunBtn"),
    heroToggleBtn: document.getElementById("heroToggleBtn"),
    newTimerBtn: document.getElementById("newTimerBtn"),
    timerList: document.getElementById("timerList"),
    timerForm: document.getElementById("timerForm"),
    timerId: document.getElementById("timerId"),
    timerName: document.getElementById("timerName"),
    timerInterval: document.getElementById("timerInterval"),
    timerLeads: document.getElementById("timerLeads"),
    timerColor: document.getElementById("timerColor"),
    timerAnchorTime: document.getElementById("timerAnchorTime"),
    timerNote: document.getElementById("timerNote"),
    timerMessageTemplate: document.getElementById("timerMessageTemplate"),
    timerEnabled: document.getElementById("timerEnabled"),
    timerIntegrationOptions: document.getElementById("timerIntegrationOptions"),
    deleteTimerBtn: document.getElementById("deleteTimerBtn"),
    resetTimerFormBtn: document.getElementById("resetTimerFormBtn"),
    integrationList: document.getElementById("integrationList"),
    integrationForm: document.getElementById("integrationForm"),
    integrationId: document.getElementById("integrationId"),
    integrationName: document.getElementById("integrationName"),
    integrationType: document.getElementById("integrationType"),
    integrationWebhook: document.getElementById("integrationWebhook"),
    integrationHeaders: document.getElementById("integrationHeaders"),
    integrationBodyTemplate: document.getElementById("integrationBodyTemplate"),
    integrationEnabled: document.getElementById("integrationEnabled"),
    integrationDefault: document.getElementById("integrationDefault"),
    integrationCommandEnabled: document.getElementById("integrationCommandEnabled"),
    integrationCommandPrefix: document.getElementById("integrationCommandPrefix"),
    integrationCommandToken: document.getElementById("integrationCommandToken"),
    newIntegrationBtn: document.getElementById("newIntegrationBtn"),
    generateTokenBtn: document.getElementById("generateTokenBtn"),
    testIntegrationBtn: document.getElementById("testIntegrationBtn"),
    deleteIntegrationBtn: document.getElementById("deleteIntegrationBtn"),
    settingsForm: document.getElementById("settingsForm"),
    settingsSiteTitle: document.getElementById("settingsSiteTitle"),
    settingsBroadcastHint: document.getElementById("settingsBroadcastHint"),
    settingsGraceSeconds: document.getElementById("settingsGraceSeconds"),
    commandEndpoint: document.getElementById("commandEndpoint"),
    commandHelp: document.getElementById("commandHelp"),
    eventList: document.getElementById("eventList"),
  });
}

function bindEvents() {
  els.exportSnapshotBtn?.addEventListener("click", exportSnapshot);
  els.newTimerBtn?.addEventListener("click", clearTimerForm);
  els.resetTimerFormBtn?.addEventListener("click", clearTimerForm);
  els.deleteTimerBtn?.addEventListener("click", deleteTimer);
  els.timerForm?.addEventListener("submit", submitTimerForm);
  els.heroResetBtn?.addEventListener("click", () => performHeroAction("reset"));
  els.heroApplyNextRunBtn?.addEventListener("click", () => performHeroAction("next-run"));
  els.heroToggleBtn?.addEventListener("click", () => performHeroAction("toggle"));
  document.querySelectorAll("[data-shift]").forEach((button) => {
    button.addEventListener("click", () => performHeroShift(Number(button.dataset.shift)));
  });

  els.newIntegrationBtn?.addEventListener("click", clearIntegrationForm);
  els.generateTokenBtn?.addEventListener("click", () => {
    els.integrationCommandToken.value = randomToken();
  });
  els.deleteIntegrationBtn?.addEventListener("click", deleteIntegration);
  els.testIntegrationBtn?.addEventListener("click", testIntegration);
  els.integrationForm?.addEventListener("submit", submitIntegrationForm);
  els.settingsForm?.addEventListener("submit", submitSettingsForm);
}

async function bootstrap() {
  await refreshSnapshot();
  connectStream();
  state.refreshTimer = window.setInterval(renderLiveClocks, 1000);
}

async function refreshSnapshot() {
  const response = await fetch("/api/snapshot");
  const snapshot = await response.json();
  state.snapshot = snapshot;
  state.serverTime = new Date(snapshot.server_time).getTime();
  state.snapshotFetchedAt = Date.now();
  ensureSelections();
  renderSnapshot();
  renderLiveClocks();
}

function ensureSelections() {
  const timers = state.snapshot?.timers || [];
  const integrations = state.snapshot?.integrations || [];
  if (!timers.some((item) => item.id === state.selectedTimerId)) {
    state.selectedTimerId = timers[0]?.id || null;
  }
  if (!integrations.some((item) => item.id === state.selectedIntegrationId)) {
    state.selectedIntegrationId = integrations[0]?.id || null;
  }
}

function renderSnapshot() {
  renderSettings();
  if (state.page === "bot") {
    renderBotPage();
  } else {
    renderDashboardPage();
  }
}

function currentServerNow() {
  if (!state.serverTime || !state.snapshotFetchedAt) {
    return Date.now();
  }
  return state.serverTime + (Date.now() - state.snapshotFetchedAt);
}

function formatCountdown(seconds) {
  const safe = Math.max(0, seconds);
  const hours = String(Math.floor(safe / 3600)).padStart(2, "0");
  const minutes = String(Math.floor((safe % 3600) / 60)).padStart(2, "0");
  const secs = String(safe % 60).padStart(2, "0");
  return `${hours}:${minutes}:${secs}`;
}

function formatDateTime(value) {
  if (!value) return "--";
  const dt = new Date(value);
  if (Number.isNaN(dt.getTime())) return value;
  return dt.toLocaleString("zh-CN", {
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
    hour12: false,
  });
}

function toLocalInputValue(value) {
  if (!value) return "";
  const dt = new Date(value);
  if (Number.isNaN(dt.getTime())) return "";
  const offset = dt.getTimezoneOffset();
  const local = new Date(dt.getTime() - offset * 60 * 1000);
  return local.toISOString().slice(0, 16);
}

function fromLocalInputValue(value) {
  if (!value) return null;
  return new Date(value).toISOString();
}

function renderSettings() {
  const settings = state.snapshot.settings || {};
  document.title = settings.site_title || "Boss 循环计时器";
  if (els.siteTitle) {
    els.siteTitle.textContent = settings.site_title || "Boss 循环计时器";
  }
  if (els.settingsSiteTitle) {
    els.settingsSiteTitle.value = settings.site_title || "";
  }
  if (els.settingsBroadcastHint) {
    els.settingsBroadcastHint.value = settings.broadcast_hint || "";
  }
  if (els.settingsGraceSeconds) {
    els.settingsGraceSeconds.value = settings.scheduler_grace_seconds || 75;
  }
}

function renderTimerList() {
  if (!els.timerList) return;
  const timers = state.snapshot.timers || [];
  if (!timers.length) {
    els.timerList.innerHTML = '<div class="empty-state">暂无计时器。</div>';
    return;
  }
  els.timerList.innerHTML = timers
    .map((timer) => {
      const countdown = computeTimerCountdown(timer);
      return `
        <button class="timer-item ${timer.id === state.selectedTimerId ? "active" : ""}" data-timer-id="${timer.id}" type="button">
          <div class="timer-title-row">
            <div>
              <div class="timer-title">${escapeHtml(timer.name)}</div>
              <div class="timer-sub">下次 ${formatDateTime(timer.next_run_at)}</div>
            </div>
            <span class="timer-status ${timer.enabled ? "status-running" : "status-paused"}">${timer.enabled ? "运行中" : "已暂停"}</span>
          </div>
          <div class="timer-countdown">${formatCountdown(countdown)}</div>
          <div class="timer-sub">循环 ${timer.interval_minutes} 分钟 · 提醒 ${timer.lead_minutes.join(" / ")}</div>
        </button>
      `;
    })
    .join("");
  els.timerList.querySelectorAll("[data-timer-id]").forEach((button) => {
    button.addEventListener("click", () => {
      state.selectedTimerId = button.dataset.timerId;
      renderSnapshot();
    });
  });
}

function renderHero() {
  if (!els.heroName || !els.heroCountdown || !els.heroNextRun || !els.heroInterval || !els.heroLeads || !els.heroProgressBar || !els.heroNextRunInput || !els.heroToggleBtn) {
    return;
  }
  const timer = selectedTimer();
  if (!timer) {
    els.heroName.textContent = "还没有计时器";
    els.heroCountdown.textContent = "00:00:00";
    els.heroNextRun.textContent = "--";
    els.heroInterval.textContent = "--";
    els.heroLeads.textContent = "--";
    els.heroProgressBar.style.width = "0%";
    return;
  }
  const countdown = computeTimerCountdown(timer);
  els.heroName.textContent = timer.name;
  els.heroCountdown.textContent = formatCountdown(countdown);
  els.heroNextRun.textContent = formatDateTime(timer.next_run_at);
  els.heroInterval.textContent = `${timer.interval_minutes} 分钟`;
  els.heroLeads.textContent = timer.lead_minutes.join(" / ");
  const total = Math.max(1, Number(timer.interval_minutes) * 60);
  const progress = ((total - countdown) / total) * 100;
  els.heroProgressBar.style.width = `${Math.max(0, Math.min(100, progress))}%`;
  els.heroNextRunInput.value = toLocalInputValue(timer.next_run_at);
  els.heroToggleBtn.textContent = timer.enabled ? "暂停计时器" : "恢复计时器";
}

function renderLiveClocks() {
  if (!state.snapshot) return;
  if (els.serverTime) {
    els.serverTime.textContent = new Date(currentServerNow()).toLocaleString("zh-CN", {
      month: "2-digit",
      day: "2-digit",
      hour: "2-digit",
      minute: "2-digit",
      second: "2-digit",
      hour12: false,
    });
  }
  if (state.page !== "bot") {
    renderHero();
    updateTimerCountdowns();
  }
}

function updateTimerCountdowns() {
  if (!els.timerList) return;
  const timers = state.snapshot?.timers || [];
  const timerMap = new Map(timers.map((timer) => [timer.id, timer]));
  els.timerList.querySelectorAll("[data-timer-id]").forEach((button) => {
    const timer = timerMap.get(button.dataset.timerId);
    if (!timer) return;
    const countdown = computeTimerCountdown(timer);
    const countdownEl = button.querySelector(".timer-countdown");
    if (countdownEl) {
      countdownEl.textContent = formatCountdown(countdown);
    }
  });
}

function renderDashboardPage() {
  renderTimerList();
  renderHero();
  renderTimerForm();
  renderEvents();
}

function renderBotPage() {
  renderIntegrationList();
  renderIntegrationForm();
  renderCommandGuide();
  renderEvents();
}

function renderTimerForm() {
  if (!els.timerForm) return;
  const timer = selectedTimer();
  if (!timer) {
    clearTimerForm();
    return;
  }
  els.timerId.value = timer.id;
  els.timerName.value = timer.name;
  els.timerInterval.value = timer.interval_minutes;
  els.timerLeads.value = timer.lead_minutes.join(",");
  els.timerColor.value = timer.color || "#ff7a59";
  els.timerAnchorTime.value = toLocalInputValue(timer.anchor_time);
  els.timerNote.value = timer.note || "";
  els.timerMessageTemplate.value = timer.message_template || "";
  els.timerEnabled.checked = Boolean(timer.enabled);
  renderIntegrationBinding(timer.integration_ids || []);
}

function renderIntegrationBinding(selectedIds) {
  if (!els.timerIntegrationOptions) return;
  const integrations = state.snapshot.integrations || [];
  if (!integrations.length) {
    els.timerIntegrationOptions.innerHTML = '<div class="empty-state">暂无通道。</div>';
    return;
  }
  els.timerIntegrationOptions.innerHTML = integrations
    .map(
      (item) => `
        <label class="check-pill">
          <input type="checkbox" value="${item.id}" ${selectedIds.includes(item.id) ? "checked" : ""} />
          <span>${escapeHtml(item.name)}${item.is_default ? " · 默认" : ""}</span>
        </label>
      `
    )
    .join("");
}

function renderIntegrationList() {
  if (!els.integrationList) return;
  const integrations = state.snapshot.integrations || [];
  if (!integrations.length) {
    els.integrationList.innerHTML = '<div class="empty-state">暂无通道。</div>';
    return;
  }
  els.integrationList.innerHTML = integrations
    .map(
      (integration) => `
        <button class="integration-item ${integration.id === state.selectedIntegrationId ? "active" : ""}" data-integration-id="${integration.id}" type="button">
          <div class="integration-title-row">
            <div>
              <div class="integration-title">${escapeHtml(integration.name)}</div>
              <div class="integration-sub">${integration.type === "wecom_group_bot" ? "企业微信群机器人" : "通用 Webhook"}</div>
            </div>
            <span class="timer-status ${integration.enabled ? "status-running" : "status-paused"}">${integration.enabled ? "可用" : "停用"}</span>
          </div>
          <div class="integration-sub">${integration.is_default ? "默认通道" : "按计时器绑定发送"}</div>
        </button>
      `
    )
    .join("");
  els.integrationList.querySelectorAll("[data-integration-id]").forEach((button) => {
    button.addEventListener("click", () => {
      state.selectedIntegrationId = button.dataset.integrationId;
      renderSnapshot();
    });
  });
}

function renderIntegrationForm() {
  if (!els.integrationForm) return;
  const integration = selectedIntegration();
  if (!integration) {
    clearIntegrationForm();
    return;
  }
  els.integrationId.value = integration.id;
  els.integrationName.value = integration.name;
  els.integrationType.value = integration.type;
  els.integrationWebhook.value = integration.webhook_url || "";
  els.integrationHeaders.value = JSON.stringify(integration.headers || {}, null, 2);
  els.integrationBodyTemplate.value = integration.body_template || "";
  els.integrationEnabled.checked = Boolean(integration.enabled);
  els.integrationDefault.checked = Boolean(integration.is_default);
  els.integrationCommandEnabled.checked = Boolean(integration.command_enabled);
  els.integrationCommandPrefix.value = integration.command_prefix || "boss";
  els.integrationCommandToken.value = integration.command_token || "";
}

function renderCommandGuide() {
  if (!els.commandEndpoint || !els.commandHelp) return;
  const integration = selectedIntegration();
  const prefix = integration?.command_prefix || "boss";
  els.commandEndpoint.textContent = `${window.location.origin}/api/commands`;
  els.commandHelp.textContent = [
    `${prefix} 帮助`,
    `${prefix} 列表`,
    `${prefix} 重置 默认 Boss`,
    `${prefix} 延后 默认 Boss 5`,
    `${prefix} 下次 默认 Boss 21:30`,
    `${prefix} 间隔 默认 Boss 31`,
    `${prefix} 提醒 默认 Boss 10,5,1,0`,
    `${prefix} 开启 默认 Boss`,
    `${prefix} 关闭 默认 Boss`,
  ].join("\n");
}

function renderEvents() {
  if (!els.eventList) return;
  const events = state.snapshot.events || [];
  if (!events.length) {
    els.eventList.innerHTML = '<div class="empty-state">当前还没有日志。</div>';
    return;
  }
  els.eventList.innerHTML = events
    .map(
      (item) => `
        <article class="event-item">
          <div class="event-title-row">
            <div class="event-title">${escapeHtml(item.title)}</div>
            <span class="event-status event-${item.status}">${labelStatus(item.status)}</span>
          </div>
          <div class="event-meta">${formatDateTime(item.created_at)} · ${escapeHtml(item.event_type)}</div>
          ${item.body ? `<div class="event-body">${escapeHtml(item.body)}</div>` : ""}
          ${item.detail ? `<div class="event-sub">${escapeHtml(item.detail)}</div>` : ""}
        </article>
      `
    )
    .join("");
}

function selectedTimer() {
  return (state.snapshot?.timers || []).find((item) => item.id === state.selectedTimerId) || null;
}

function selectedIntegration() {
  return (state.snapshot?.integrations || []).find((item) => item.id === state.selectedIntegrationId) || null;
}

function computeTimerCountdown(timer) {
  const next = new Date(timer.next_run_at).getTime();
  const intervalSeconds = Math.max(1, Number(timer.interval_minutes) * 60);
  let seconds = Math.floor((next - currentServerNow()) / 1000);
  while (seconds < 0) {
    seconds += intervalSeconds;
  }
  return seconds;
}

async function submitTimerForm(event) {
  event.preventDefault();
  const payload = {
    name: els.timerName.value.trim(),
    interval_minutes: Number(els.timerInterval.value),
    lead_minutes: parseLeadMinutes(els.timerLeads.value),
    anchor_time: fromLocalInputValue(els.timerAnchorTime.value),
    enabled: els.timerEnabled.checked,
    color: els.timerColor.value,
    note: els.timerNote.value.trim(),
    message_template: els.timerMessageTemplate.value.trim(),
    integration_ids: Array.from(els.timerIntegrationOptions?.querySelectorAll("input:checked") || []).map((input) => input.value),
  };
  if (!payload.name) {
    alert("请填写计时器名称。");
    return;
  }
  const timerId = els.timerId.value;
  const response = await fetch(timerId ? `/api/timers/${timerId}` : "/api/timers", {
    method: timerId ? "PUT" : "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  if (!response.ok) {
    alert(await response.text());
    return;
  }
  const data = await response.json();
  state.selectedTimerId = data.id;
  await refreshSnapshot();
}

async function deleteTimer() {
  const timer = selectedTimer();
  if (!timer || !confirm(`确定删除 ${timer.name} 吗？`)) return;
  const response = await fetch(`/api/timers/${timer.id}`, { method: "DELETE" });
  if (!response.ok) {
    alert(await response.text());
    return;
  }
  state.selectedTimerId = null;
  await refreshSnapshot();
}

function clearTimerForm() {
  if (!els.timerForm) return;
  els.timerForm.reset();
  els.timerId.value = "";
  els.timerColor.value = "#ff7a59";
  els.timerEnabled.checked = true;
  els.timerLeads.value = "5,1,0";
  els.timerAnchorTime.value = toLocalInputValue(new Date().toISOString());
  renderIntegrationBinding([]);
}

async function performHeroAction(action) {
  if (!els.heroNextRunInput || !els.heroToggleBtn) return;
  const timer = selectedTimer();
  if (!timer) return;
  let response;
  if (action === "reset") {
    response = await fetch(`/api/timers/${timer.id}/reset`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({}),
    });
  } else if (action === "toggle") {
    response = await fetch(`/api/timers/${timer.id}/toggle`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ enabled: !timer.enabled }),
    });
  } else if (action === "next-run") {
    if (!els.heroNextRunInput.value) {
      alert("先选择一个时间。");
      return;
    }
    response = await fetch(`/api/timers/${timer.id}/next-run`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ next_run_at: fromLocalInputValue(els.heroNextRunInput.value) }),
    });
  }
  if (!response || !response.ok) {
    alert(response ? await response.text() : "执行失败。");
    return;
  }
  await refreshSnapshot();
}

async function performHeroShift(minutes) {
  const timer = selectedTimer();
  if (!timer) return;
  const response = await fetch(`/api/timers/${timer.id}/shift`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ minutes }),
  });
  if (!response.ok) {
    alert(await response.text());
    return;
  }
  await refreshSnapshot();
}

async function submitIntegrationForm(event) {
  event.preventDefault();
  let headers = {};
  if (els.integrationHeaders.value.trim()) {
    try {
      headers = JSON.parse(els.integrationHeaders.value);
    } catch (error) {
      alert("请求头 JSON 格式不对。");
      return;
    }
  }
  const payload = {
    name: els.integrationName.value.trim(),
    type: els.integrationType.value,
    enabled: els.integrationEnabled.checked,
    is_default: els.integrationDefault.checked,
    webhook_url: els.integrationWebhook.value.trim(),
    headers,
    body_template: els.integrationBodyTemplate.value.trim(),
    command_enabled: els.integrationCommandEnabled.checked,
    command_prefix: els.integrationCommandPrefix.value.trim() || "boss",
    command_token: els.integrationCommandToken.value.trim(),
  };
  if (!payload.name) {
    alert("请填写通道名称。");
    return;
  }
  const integrationId = els.integrationId.value;
  const response = await fetch(integrationId ? `/api/integrations/${integrationId}` : "/api/integrations", {
    method: integrationId ? "PUT" : "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  if (!response.ok) {
    alert(await response.text());
    return;
  }
  const data = await response.json();
  state.selectedIntegrationId = data.id;
  await refreshSnapshot();
}

async function deleteIntegration() {
  const integration = selectedIntegration();
  if (!integration || !confirm(`确定删除 ${integration.name} 吗？`)) return;
  const response = await fetch(`/api/integrations/${integration.id}`, { method: "DELETE" });
  if (!response.ok) {
    alert(await response.text());
    return;
  }
  state.selectedIntegrationId = null;
  await refreshSnapshot();
}

function clearIntegrationForm() {
  if (!els.integrationForm) return;
  els.integrationForm.reset();
  els.integrationId.value = "";
  els.integrationType.value = "wecom_group_bot";
  els.integrationEnabled.checked = true;
  els.integrationDefault.checked = false;
  els.integrationHeaders.value = "{}";
  els.integrationCommandPrefix.value = "boss";
}

async function testIntegration() {
  const integration = selectedIntegration();
  if (!integration) {
    alert("请先选择一个通道。");
    return;
  }
  const response = await fetch(`/api/integrations/${integration.id}/test`, { method: "POST" });
  const data = await response.json();
  alert(data.detail || (data.ok ? "测试成功" : "测试失败"));
  await refreshSnapshot();
}

async function submitSettingsForm(event) {
  event.preventDefault();
  const payload = {
    site_title: els.settingsSiteTitle.value.trim(),
    broadcast_hint: els.settingsBroadcastHint.value.trim(),
    scheduler_grace_seconds: Number(els.settingsGraceSeconds.value),
  };
  const response = await fetch("/api/settings", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  if (!response.ok) {
    alert(await response.text());
    return;
  }
  await refreshSnapshot();
}

function connectStream() {
  if (state.eventSource) {
    state.eventSource.close();
  }
  const source = new EventSource("/api/stream");
  state.eventSource = source;
  source.onopen = () => {
    els.liveState.textContent = "已连接";
  };
  source.onmessage = async (event) => {
    const payload = JSON.parse(event.data);
    if (payload.type === "hello" || payload.type === "tick") {
      return;
    }
    try {
      await refreshSnapshot();
    } catch (error) {
      console.error(error);
    }
  };
  source.onerror = () => {
    els.liveState.textContent = "重连中";
  };
}

function exportSnapshot() {
  if (!state.snapshot) return;
  const blob = new Blob([JSON.stringify(state.snapshot, null, 2)], { type: "application/json" });
  const url = URL.createObjectURL(blob);
  const anchor = document.createElement("a");
  anchor.href = url;
  anchor.download = `boss-loop-snapshot-${Date.now()}.json`;
  anchor.click();
  URL.revokeObjectURL(url);
}

function parseLeadMinutes(raw) {
  const values = raw
    .replaceAll("，", ",")
    .split(",")
    .map((part) => Number(part.trim()))
    .filter((value) => !Number.isNaN(value) && value >= 0);
  return [...new Set([...(values.length ? values : [5, 1, 0]), 0])].sort((a, b) => b - a);
}

function labelStatus(status) {
  if (status === "success") return "成功";
  if (status === "warning") return "警告";
  if (status === "error") return "失败";
  return "信息";
}

function randomToken() {
  const source = Math.random().toString(36).slice(2, 10);
  return `bridge-${source}`;
}

function escapeHtml(value) {
  return String(value ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#39;");
}
