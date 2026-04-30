from __future__ import annotations

import logging
import os
import traceback
from contextlib import asynccontextmanager
from datetime import datetime, timezone

from dotenv import load_dotenv
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

from pathlib import Path

from src.config_loader import load_config
from src.game import WerewolfGame

load_dotenv()

DEFAULT_CONFIG = Path(__file__).parent.parent / "configs" / "default-8p.yaml"

_current_game: WerewolfGame | None = None

logger = logging.getLogger("werewolf")


@asynccontextmanager
async def lifespan(app: FastAPI):
    yield


app = FastAPI(lifespan=lifespan)


@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    logger.error("Unhandled exception: %s\n%s", exc, traceback.format_exc())
    return JSONResponse(
        status_code=500,
        content={"error": f"服务器内部错误: {exc}"},
    )


@app.get("/api/health")
async def health():
    return {
        "status": "ok",
        "model": os.getenv("SILICONFLOW_MODEL", ""),
        "gm_model": os.getenv("SILICONFLOW_GM_MODEL", ""),
    }


@app.post("/api/game/new")
async def new_game(config_path: str | None = None):
    global _current_game
    path = Path(config_path) if config_path else DEFAULT_CONFIG
    config = load_config(path)
    _current_game = WerewolfGame(config)
    return {"state": _serialize_state(_current_game.state)}


@app.post("/api/game/step")
async def step_game():
    global _current_game
    if not _current_game:
        return {"error": "No active game. POST /api/game/new first."}
    await _current_game.run_one_step()
    return {"state": _serialize_state(_current_game.state)}


@app.post("/api/game/run")
async def run_game(max_steps: int = 120):
    global _current_game
    if not _current_game:
        return {"error": "No active game. POST /api/game/new first."}
    steps = 0
    while _current_game.state.winner == "none" and steps < max_steps:
        await _current_game.run_one_step()
        steps += 1
    return {"state": _serialize_state(_current_game.state)}


def _serialize_state(state) -> dict:
    finished = state.winner != "none"
    next_phase = "day" if state.phase == "night" else "night"

    timeline_lines: list[str] = []
    public_events: list[dict] = []

    for e in state.timeline:
        if e.type == "death":
            emoji = "🌙" if e.phase == "night" else "☀️"
            timeline_lines.append(f"{emoji} Day{e.day} {e.phase}: {e.content}")
        elif e.type == "speech":
            timeline_lines.append(f"🗣️ {e.speaker}: {e.content}")
        elif e.type == "summary":
            timeline_lines.append(f"📋 GM摘要：{e.content}")
        else:
            timeline_lines.append(f"  {e.speaker}: {e.content}")

        public_events.append({
            "day": e.day,
            "phase": e.phase,
            "type": e.type,
            "speaker": e.speaker,
            "content": e.content,
        })

    return {
        "id": state.game_id,
        "currentDay": state.current_day,
        "nextPhase": next_phase if not finished else "finished",
        "finished": finished,
        "winner": state.winner,
        "alivePlayers": list(state.alive_players),
        "roles": state.roles,
        "timeline": timeline_lines,
        "publicEventLog": public_events,
        "lastUpdatedAt": datetime.now(timezone.utc).isoformat(),
    }


app.mount("/", StaticFiles(directory="public", html=True), name="static")
