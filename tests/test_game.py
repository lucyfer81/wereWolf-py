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


def test_evidence_facts_filters_night_events():
    """evidence_facts 应该只包含白天阶段的事件（speech, vote, summary）以及死亡事件"""
    from src.models import GameState, PublicEvent
    from src.config_loader import load_config
    from src.game import WerewolfGame

    state = GameState(alive_players=["Seat1", "Seat2", "Seat3"])
    # Night death (death events should be included regardless of phase)
    state.add_public_event(PublicEvent(
        day=1, phase="night", type="death",
        speaker="GameMaster", content="Seat4 被杀害",
        alive_players=["Seat1", "Seat2", "Seat3"]
    ))
    # Day speech (should be included)
    state.add_public_event(PublicEvent(
        day=1, phase="day", type="speech",
        speaker="Seat1", content="我怀疑Seat2",
        alive_players=["Seat1", "Seat2", "Seat3"]
    ))
    # Day vote (should be included)
    state.add_public_event(PublicEvent(
        day=1, phase="day", type="vote",
        speaker="Seat1", content="Seat1 投票给 Seat2",
        alive_players=["Seat1", "Seat2", "Seat3"]
    ))
    # Night summary (should be EXCLUDED - it's phase=night, type=summary)
    state.add_public_event(PublicEvent(
        day=1, phase="night", type="summary",
        speaker="GameMaster", content="夜间总结",
        alive_players=["Seat1", "Seat2", "Seat3"]
    ))

    config = load_config(Path(__file__).parent / "fixtures" / "default-8p.yaml")
    game = WerewolfGame.__new__(WerewolfGame)
    game.state = state
    game.config = config

    facts = game._build_evidence_facts()
    assert "Seat4 被杀害" in facts
    assert "我怀疑Seat2" in facts
    assert "Seat1 投票给 Seat2" in facts
    assert "夜间总结" not in facts
