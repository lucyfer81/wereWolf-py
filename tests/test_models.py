from src.models import (
    PlayerMemory,
    WerewolfSharedMemory,
    GameMemory,
    SpeechRecord,
    VoteRecord,
    create_new_game_state,
)


def test_create_new_game():
    state = create_new_game_state()
    assert len(state.alive_players) == 8
    assert state.alive_players == [
        "Seat1", "Seat2", "Seat3", "Seat4",
        "Seat5", "Seat6", "Seat7", "Seat8",
    ]
    wolves = [p for p in state.alive_players if state.roles[p] == "werewolf"]
    assert len(wolves) == 2
    assert state.current_day == 1
    assert state.phase == "night"
    assert state.winner == "none"


def test_check_win_villagers():
    state = create_new_game_state()
    wolves = [p for p in state.roles if state.roles[p] == "werewolf"]
    for w in wolves:
        state.alive_players.remove(w)
    assert state.check_win() == "villagers"


def test_check_win_werewolves():
    state = create_new_game_state()
    villagers = [p for p in state.roles if state.roles[p] == "villager"]
    for v in villagers[1:]:
        state.alive_players.remove(v)
    assert state.check_win() == "werewolves"


def test_check_win_none():
    state = create_new_game_state()
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
    ctx = gm.get_prompt_context("Seat1", "villager", 1)
    assert ctx == ""


def test_game_memory_context_werewolf():
    gm = GameMemory()
    gm.player_memories["Seat3"] = PlayerMemory()
    gm.werewolf_memory = WerewolfSharedMemory(teammates=["Seat3", "Seat7"])
    ctx = gm.get_prompt_context("Seat3", "werewolf", 1)
    assert "狼人私有信息" in ctx
    assert "Seat7" in ctx


def test_sort_alive():
    state = create_new_game_state()
    state.alive_players = ["Seat5", "Seat2", "Seat8"]
    assert state.sort_alive() == ["Seat2", "Seat5", "Seat8"]


def test_game_has_game_id():
    state = create_new_game_state()
    assert len(state.game_id) == 8
