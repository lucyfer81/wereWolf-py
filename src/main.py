from __future__ import annotations

import os
from contextlib import asynccontextmanager

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
    state = _current_game.state
    return {
        "game_id": state.game_id,
        "alive_players": state.alive_players,
        "phase": state.phase,
        "current_day": state.current_day,
        "winner": state.winner,
        "roles": state.roles,
    }


@app.post("/api/game/step")
async def step_game():
    global _current_game
    if not _current_game:
        return {"error": "No active game. POST /api/game/new first."}
    state = await _current_game.run_one_step()
    return _serialize_state(state)


@app.post("/api/game/run")
async def run_game(max_steps: int = 120):
    global _current_game
    if not _current_game:
        return {"error": "No active game. POST /api/game/new first."}
    steps = 0
    while _current_game.state.winner == "none" and steps < max_steps:
        await _current_game.run_one_step()
        steps += 1
    return _serialize_state(_current_game.state)


def _serialize_state(state) -> dict:
    return {
        "game_id": state.game_id,
        "current_day": state.current_day,
        "phase": state.phase,
        "winner": state.winner,
        "alive_players": state.alive_players,
        "roles": state.roles,
        "timeline": [
            {
                "day": e.day,
                "phase": e.phase,
                "type": e.type,
                "speaker": e.speaker,
                "content": e.content,
                "alive_players": e.alive_players,
            }
            for e in state.timeline
        ],
        "day_progress": {
            "stage": state.day_progress.stage,
            "speeches": state.day_progress.speeches,
            "day_summary": state.day_progress.day_summary,
        },
    }


@app.get("/")
async def index():
    return FileResponse("public/index.html")


app.mount("/static", StaticFiles(directory="public"), name="static")
