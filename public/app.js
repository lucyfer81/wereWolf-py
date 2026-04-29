let currentState = null;
let busy = false;

const ui = {
  newBtn: document.getElementById("new-game-btn"),
  stepBtn: document.getElementById("step-btn"),
  runBtn: document.getElementById("run-btn"),
  exportLogBtn: document.getElementById("export-log-btn"),
  maxStepsInput: document.getElementById("max-steps-input"),
  statusList: document.getElementById("status-list"),
  aliveList: document.getElementById("alive-list"),
  rolesList: document.getElementById("roles-list"),
  timeline: document.getElementById("timeline"),
  eventsBody: document.getElementById("events-body"),
};

function updateExportLogButtonState() {
  const hasTimeline = Boolean(currentState?.timeline?.length);
  ui.exportLogBtn.disabled = busy || !hasTimeline;
}

function setBusy(nextBusy) {
  busy = nextBusy;
  [ui.newBtn, ui.stepBtn, ui.runBtn].forEach((btn) => {
    btn.disabled = busy;
  });
  updateExportLogButtonState();
}

async function requestJson(path, payload) {
  const response = await fetch(path, {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify(payload ?? {}),
  });
  const data = await response.json();
  if (!response.ok) {
    throw new Error(data.error || `请求失败: ${response.status}`);
  }
  return data;
}

function renderStatus() {
  const statusRows = [
    ["Game ID", currentState?.id ?? "-"],
    ["Day", currentState ? String(currentState.currentDay) : "-"],
    ["Next Phase", currentState?.nextPhase ?? "-"],
    ["Alive", currentState ? String(currentState.alivePlayers.length) : "-"],
    ["Winner", currentState?.winner ?? "-"],
    ["Finished", currentState ? String(Boolean(currentState.finished)) : "-"],
    ["Updated", currentState?.lastUpdatedAt ?? "-"],
  ];

  ui.statusList.innerHTML = statusRows
    .map(([key, value]) => `<div><dt>${key}</dt><dd>${value}</dd></div>`)
    .join("");
}

function renderChips() {
  ui.aliveList.innerHTML = "";
  if (!currentState?.alivePlayers?.length) {
    ui.aliveList.innerHTML = `<span class="chip">-</span>`;
  } else {
    currentState.alivePlayers.forEach((seat) => {
      const chip = document.createElement("span");
      chip.className = "chip";
      chip.textContent = seat;
      ui.aliveList.appendChild(chip);
    });
  }

  ui.rolesList.innerHTML = "";
  if (!currentState?.roles) {
    ui.rolesList.innerHTML = `<span class="chip">-</span>`;
    return;
  }
  Object.entries(currentState.roles)
    .sort((a, b) => Number(a[0].replace("Seat", "")) - Number(b[0].replace("Seat", "")))
    .forEach(([seat, role]) => {
      const chip = document.createElement("span");
      chip.className = `chip ${role}`;
      chip.textContent = `${seat} · ${role}`;
      ui.rolesList.appendChild(chip);
    });
}

function renderTimeline() {
  const timeline = currentState?.timeline ?? [];
  if (!timeline.length) {
    ui.timeline.textContent = "暂无日志。";
    ui.timeline.classList.add("empty");
    updateExportLogButtonState();
    return;
  }
  ui.timeline.textContent = timeline.join("\n");
  ui.timeline.classList.remove("empty");
  ui.timeline.scrollTop = ui.timeline.scrollHeight;
  updateExportLogButtonState();
}

function buildExportFileName() {
  const gameId = String(currentState?.id ?? "unknown")
    .replace(/[^a-zA-Z0-9_-]+/g, "-")
    .replace(/-+/g, "-")
    .replace(/^-|-$/g, "");
  const timestamp = new Date().toISOString().replace(/\.\d{3}Z$/, "Z").replace(/:/g, "-");
  return `werewolf-log-${gameId || "unknown"}-${timestamp}.md`;
}

function buildTimelineMarkdown() {
  const timelineLines = currentState?.timeline ?? [];
  const timelineText = timelineLines.join("\n").replace(/```/g, "``\\`");
  const alivePlayers = currentState?.alivePlayers?.length ? currentState.alivePlayers.join(", ") : "-";
  const exportedAt = new Date().toISOString();

  return [
    "# AI 狼人杀运行日志",
    "",
    `- 导出时间: ${exportedAt}`,
    `- Game ID: ${currentState?.id ?? "-"}`,
    `- Day: ${currentState?.currentDay ?? "-"}`,
    `- Next Phase: ${currentState?.nextPhase ?? "-"}`,
    `- Finished: ${String(Boolean(currentState?.finished))}`,
    `- Winner: ${currentState?.winner ?? "-"}`,
    `- Alive Players: ${alivePlayers}`,
    "",
    "## 时间线日志",
    "",
    "```text",
    timelineText || "暂无日志。",
    "```",
    "",
  ].join("\n");
}

function exportTimelineAsMarkdown() {
  const timeline = currentState?.timeline ?? [];
  if (!timeline.length) {
    alert("当前没有可导出的时间线日志。");
    updateExportLogButtonState();
    return;
  }

  const markdown = buildTimelineMarkdown();
  const blob = new Blob([markdown], { type: "text/markdown;charset=utf-8" });
  const downloadUrl = URL.createObjectURL(blob);
  const anchor = document.createElement("a");
  anchor.href = downloadUrl;
  anchor.download = buildExportFileName();
  document.body.appendChild(anchor);
  anchor.click();
  anchor.remove();
  URL.revokeObjectURL(downloadUrl);
}

function renderEvents() {
  const events = currentState?.publicEventLog ?? [];
  ui.eventsBody.innerHTML = "";
  if (!events.length) {
    ui.eventsBody.innerHTML = `<tr><td colspan="5">暂无公共事件</td></tr>`;
    return;
  }
  events.forEach((event) => {
    const tr = document.createElement("tr");
    tr.innerHTML = `
      <td>${event.day}</td>
      <td>${event.phase}</td>
      <td>${event.type}</td>
      <td>${event.speaker}</td>
      <td>${event.content}</td>
    `;
    ui.eventsBody.appendChild(tr);
  });
}

function renderAll() {
  renderStatus();
  renderChips();
  renderTimeline();
  renderEvents();
}

async function createNewGame() {
  setBusy(true);
  try {
    const result = await requestJson("/api/game/new");
    currentState = result.state;
    renderAll();
  } finally {
    setBusy(false);
  }
}

async function stepGame() {
  if (!currentState) return;
  setBusy(true);
  try {
    const result = await requestJson("/api/game/step", { state: currentState });
    currentState = result.state;
    renderAll();
  } finally {
    setBusy(false);
  }
}

async function runGameToEnd() {
  const originalLabel = ui.runBtn.textContent;
  setBusy(true);
  try {
    const maxSteps = Number(ui.maxStepsInput.value) || 120;
    if (!currentState) {
      const result = await requestJson("/api/game/new");
      currentState = result.state;
      renderAll();
    }

    let stepsTaken = 0;
    for (; stepsTaken < maxSteps; stepsTaken += 1) {
      if (!currentState || currentState.finished) break;
      ui.runBtn.textContent = `自动运行中 ${stepsTaken + 1}/${maxSteps}`;
      const result = await requestJson("/api/game/step", { state: currentState });
      currentState = result.state;
      renderAll();
      // Give the browser a moment to paint each intermediate state.
      // eslint-disable-next-line no-await-in-loop
      await new Promise((resolve) => setTimeout(resolve, 60));
    }

    if (!currentState?.finished && stepsTaken >= maxSteps) {
      alert("达到最大步数限制，游戏未结束。可以继续点击“自动跑到结束”。");
    }
  } finally {
    ui.runBtn.textContent = originalLabel;
    setBusy(false);
  }
}

ui.newBtn.addEventListener("click", () => {
  createNewGame().catch((error) => alert(String(error)));
});

ui.stepBtn.addEventListener("click", () => {
  stepGame().catch((error) => alert(String(error)));
});

ui.runBtn.addEventListener("click", () => {
  runGameToEnd().catch((error) => alert(String(error)));
});

ui.exportLogBtn.addEventListener("click", () => {
  exportTimelineAsMarkdown();
});

window.render_game_to_text = () => {
  return JSON.stringify(
    {
      mode: !currentState ? "idle" : currentState.finished ? "finished" : "running",
      day: currentState?.currentDay ?? 0,
      nextPhase: currentState?.nextPhase ?? null,
      alivePlayers: currentState?.alivePlayers ?? [],
      winner: currentState?.winner ?? "none",
      coordinate_system: "not_applicable_seat_based",
    },
    null,
    2,
  );
};

window.advanceTime = async (ms) => {
  if (!currentState || currentState.finished) return;
  const steps = Math.max(1, Math.round(ms / 900));
  for (let i = 0; i < steps; i += 1) {
    if (currentState.finished) break;
    // eslint-disable-next-line no-await-in-loop
    await stepGame();
  }
};

renderAll();
