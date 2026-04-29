from __future__ import annotations

import os
from contextlib import asynccontextmanager
from datetime import datetime, timezone

from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from src.game import WerewolfGame

load_dotenv()

_current_game: WerewolfGame | None = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    yield


app = FastAPI(lifespan=lifespan)


@app.get("/api/health")
async def health():
    return {
        "status": "ok",
        "model": os.getenv("SILICONFLOW_MODEL", ""),
        "gm_model": os.getenv("SILICONFLOW_GM_MODEL", ""),
    }


@app.post("/api/game/new")
async def new_game():
    global _current_game
    _current_game = WerewolfGame()
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


@app.get("/")
async def index():
    return FileResponse("public/index.html")


app.mount("/static", StaticFiles(directory="public"), name="static")
