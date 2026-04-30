import pytest
from pathlib import Path

from src.config_loader import load_config, GameConfig
from src.models import (
    PlayerMemory,
    WerewolfSharedMemory,
    GameMemory,
    SpeechRecord,
    VoteRecord,
    WitchState,
    SeerResult,
    create_new_game_state,
)

FIXTURE_DIR = Path(__file__).parent / "fixtures"


@pytest.fixture
def config() -> GameConfig:
    return load_config(FIXTURE_DIR / "default-8p.yaml")


def test_create_new_game(config):
    state = create_new_game_state(config)
    assert len(state.alive_players) == 8
    assert state.alive_players == [
        "Seat1", "Seat2", "Seat3", "Seat4",
        "Seat5", "Seat6", "Seat7", "Seat8",
    ]
    wolves = [p for p in state.alive_players if state.role_teams.get(state.roles[p]) == "werewolves"]
    assert len(wolves) == 3
    assert state.current_day == 1
    assert state.phase == "night"
    assert state.winner == "none"


def test_check_win_villagers(config):
    state = create_new_game_state(config)
    wolves = [p for p in state.roles if state.role_teams.get(state.roles[p]) == "werewolves"]
    for w in wolves:
        state.alive_players.remove(w)
    assert state.check_win() == "villagers"


def test_check_win_werewolves(config):
    state = create_new_game_state(config)
    villagers = [p for p in state.roles if state.role_teams.get(state.roles[p]) == "villagers"]
    for v in villagers[1:]:
        state.alive_players.remove(v)
    assert state.check_win() == "werewolves"


def test_check_win_none(config):
    state = create_new_game_state(config)
    assert state.check_win() == "none"


def test_player_memory():
    mem = PlayerMemory()
    mem.speech_log[1] = [
        SpeechRecord(speaker="Seat1", content="我怀疑Seat3", target="Seat3")
    ]
    assert len(mem.speech_log[1]) == 1
    assert mem.speech_log[1][0].speaker == "Seat1"


def test_player_memory_day_context():
    mem = PlayerMemory()
    mem.speech_log[1] = [
        SpeechRecord(speaker="Seat1", content="我怀疑Seat3", target="Seat3")
    ]
    mem.vote_log[1] = [
        VoteRecord(
            voter="Seat1", target="Seat3", alt_target="Seat5",
            confidence="high", risk_if_wrong="可能误杀",
            target_vs_alt_reason="Seat3更可疑",
        )
    ]
    mem.death_log[1] = "Seat3"
    ctx = mem.get_day_context(1)
    assert "Seat1" in ctx
    assert "Seat3" in ctx
    assert "死亡" in ctx


def test_player_memory_reflections():
    mem = PlayerMemory()
    assert mem.get_reflections_str() == ""
    mem.reflections.append("Seat3的行为很可疑")
    assert "Seat3" in mem.get_reflections_str()


def test_werewolf_shared_memory():
    wm = WerewolfSharedMemory(teammates=["Seat3", "Seat7"])
    wm.kills[1] = "Seat1"
    text = wm.to_str(1)
    assert "Seat3" in text
    assert "Seat7" in text
    assert "Seat1" in text


def test_game_memory_context_villager():
    gm = GameMemory()
    gm.player_memories["Seat1"] = PlayerMemory()
    role_teams = {"villager": "villagers", "werewolf": "werewolves"}
    ctx = gm.get_prompt_context("Seat1", "villager", role_teams, 1)
    assert ctx == ""


def test_game_memory_context_werewolf():
    gm = GameMemory()
    gm.player_memories["Seat3"] = PlayerMemory()
    gm.werewolf_memory = WerewolfSharedMemory(teammates=["Seat3", "Seat7"])
    role_teams = {"villager": "villagers", "werewolf": "werewolves"}
    ctx = gm.get_prompt_context("Seat3", "werewolf", role_teams, 1)
    assert "狼人私有信息" in ctx
    assert "Seat7" in ctx


def test_sort_alive(config):
    state = create_new_game_state(config)
    state.alive_players = ["Seat5", "Seat2", "Seat8"]
    assert state.sort_alive() == ["Seat2", "Seat5", "Seat8"]


def test_game_has_game_id(config):
    state = create_new_game_state(config)
    assert len(state.game_id) == 8


def test_create_9p_game():
    config = load_config(FIXTURE_DIR / "classic-9p.yaml")
    state = create_new_game_state(config)
    assert len(state.alive_players) == 9
    role_counts: dict[str, int] = {}
    for p in state.alive_players:
        r = state.roles[p]
        role_counts[r] = role_counts.get(r, 0) + 1
    assert role_counts["werewolf"] == 3
    assert role_counts["seer"] == 1
    assert role_counts["witch"] == 1
    assert role_counts["guard"] == 1
    assert role_counts["villager"] == 3


def test_witch_state():
    ws = WitchState()
    assert ws.antidote_used is False
    assert ws.poison_used is False
    ws.antidote_used = True
    assert ws.antidote_used is True


def test_seer_result():
    sr = SeerResult(day=1, target="Seat3", result="werewolf")
    assert sr.day == 1
    assert sr.target == "Seat3"
    assert sr.result == "werewolf"


def test_player_memory_seer_results():
    mem = PlayerMemory()
    mem.seer_results.append(SeerResult(day=1, target="Seat3", result="werewolf"))
    assert len(mem.seer_results) == 1
    assert mem.seer_results[0].result == "werewolf"


def test_player_memory_role_state():
    mem = PlayerMemory()
    mem.role_state = {"antidote_used": False, "poison_used": False}
    assert mem.role_state is not None
    assert mem.role_state["antidote_used"] is False
