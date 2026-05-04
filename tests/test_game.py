import json

import pytest
from pathlib import Path

from src.config_loader import load_config, GameConfig
from src.game import (
    WerewolfGame,
    validate_speech,
    validate_vote,
    build_fallback_speech,
    build_fallback_vote,
)

FIXTURE_DIR = Path(__file__).parent / "fixtures"


@pytest.fixture
def config() -> GameConfig:
    return load_config(FIXTURE_DIR / "default-8p.yaml")


@pytest.fixture
def game(config) -> WerewolfGame:
    return WerewolfGame(config)


def test_create_game(game):
    state = game.state
    assert state.current_day == 1
    assert state.phase == "night"
    assert len(state.alive_players) == 8


def test_game_has_three_wolves(game):
    wolves = [
        p for p in game.state.roles
        if game.state.role_teams.get(game.state.roles[p]) == "werewolves"
    ]
    assert len(wolves) == 3


def test_validate_speech_ok():
    assert validate_speech("Seat1", "我觉得Seat3很可疑", "Seat3", ["Seat1", "Seat3"], 2) is None


def test_validate_speech_empty():
    assert validate_speech("Seat1", "", "Seat3", ["Seat1", "Seat3"], 2) is not None


def test_validate_speech_self_accusation():
    result = validate_speech("Seat1", "我怀疑自己是狼", "Seat1", ["Seat1", "Seat3"], 2)
    assert result is not None


def test_validate_speech_day1_no_target_required():
    assert validate_speech("Seat1", "观望", "", ["Seat1", "Seat3"], 1) is None


def test_validate_speech_day2_self_target():
    result = validate_speech("Seat1", "我觉得Seat3可疑", "Seat1", ["Seat1", "Seat3"], 2)
    assert result is not None


def test_validate_vote_ok():
    assert (
        validate_vote("Seat1", "Seat3", "Seat5", alive=["Seat1", "Seat3", "Seat5", "Seat7"])
        is None
    )


def test_validate_vote_same_target():
    result = validate_vote("Seat1", "Seat3", "Seat3", alive=["Seat1", "Seat3", "Seat5"])
    assert result is not None


def test_validate_vote_dead_target():
    result = validate_vote("Seat1", "Seat9", "Seat3", alive=["Seat1", "Seat3"])
    assert result is not None


def test_validate_vote_self_alt():
    result = validate_vote("Seat1", "Seat3", "Seat1", alive=["Seat1", "Seat3"])
    assert result is not None


def test_fallback_speech():
    result = build_fallback_speech("Seat1", ["Seat1", "Seat3", "Seat5"], 2)
    assert result["content"]
    assert result["target"]


def test_fallback_speech_day1():
    result = build_fallback_speech("Seat1", ["Seat1", "Seat3", "Seat5"], 1)
    assert "观望" in result["content"] or "信息有限" in result["content"]


def test_fallback_vote():
    result = build_fallback_vote("Seat1", ["Seat1", "Seat3", "Seat5"])
    assert result["target"] in ("Seat3", "Seat5")  # fallback votes for random other
    assert result["confidence"] == "low"


def test_game_state_serializable(game):
    state = game.state
    assert state.game_id
    assert isinstance(state.roles, dict)
    assert isinstance(state.alive_players, list)


def test_game_creates_log_file(config, tmp_path):
    from src.logger import GameLogger
    game = WerewolfGame(config, log_dir=tmp_path)
    assert game.log is not None
    log_file = tmp_path / f"game-{game.state.game_id}.jsonl"
    assert log_file.exists()
    records = [json.loads(line) for line in log_file.read_text().strip().split("\n") if line]
    assert records[0]["type"] == "game_start"
    assert records[0]["game_id"] == game.state.game_id
    assert "roles" in records[0]
