from src.styles import VOTING_STYLE_CARDS, get_style_for_player
from src.prompts import (
    build_player_system_prompt,
    build_gm_system_prompt,
    build_night_task,
    build_speech_task,
    build_first_vote_task,
    build_second_vote_task,
    build_summary_task,
)


def test_all_styles_present():
    assert set(VOTING_STYLE_CARDS.keys()) == {
        "conservative", "pressure", "contrarian", "logic_driven"
    }


def test_style_has_chinese_name():
    for key, card in VOTING_STYLE_CARDS.items():
        assert card["name"], f"{key} missing name"
        assert card["rules"], f"{key} missing rules"
        assert len(card["scenarios"]) >= 1, f"{key} missing scenarios"


def test_get_style_for_player():
    assert get_style_for_player("Seat1") == "conservative"
    assert get_style_for_player("Seat4") == "pressure"
    assert get_style_for_player("Seat7") == "contrarian"
    assert get_style_for_player("Seat2") == "logic_driven"


def test_player_system_prompt_werewolf():
    prompt = build_player_system_prompt(
        "Seat3", "werewolf", "你是狼人。你的同伴是：Seat2",
        "反共识型", "当多人迅速聚焦同一目标时...", "场景1：...", "夜晚时，与同伴商议并选择一个村民进行击杀。",
    )
    assert "Seat3" in prompt
    assert "狼人" in prompt
    assert "Seat2" in prompt
    assert "反共识型" in prompt
    assert "夜" in prompt


def test_player_system_prompt_villager():
    prompt = build_player_system_prompt(
        "Seat1", "villager", "你是村民。你不知道其他任何人的身份。",
        "保守谨慎型", "无确凿证据时弃票...", "场景1：...", "夜晚时，村民没有行动，请等待天亮。",
    )
    assert "Seat1" in prompt
    assert "村民" in prompt


def test_gm_system_prompt():
    prompt = build_gm_system_prompt()
    assert "管理员" in prompt
    assert "JSON" in prompt


def test_night_task():
    task = build_night_task(
        day=2, teammates=["Seat3", "Seat7"], alive_players=["Seat1", "Seat3", "Seat5", "Seat7"]
    )
    assert "第 2 天夜晚" in task
    assert "Seat3" in task
    assert "Seat7" in task
    assert "击杀目标" in task


def test_night_task_with_observation():
    task = build_night_task(
        day=2, teammates=["Seat7"], alive_players=["Seat1", "Seat3", "Seat5", "Seat7"],
        observation="Seat5的行为可疑"
    )
    assert "观察对象" in task
    assert "Seat5" in task


def test_speech_task_day1():
    task = build_speech_task(
        player="Seat1", role="villager", day=1,
        alive=["Seat1", "Seat2", "Seat3", "Seat4", "Seat5", "Seat6", "Seat7", "Seat8"],
        prior_speeches={}, observation="", evidence_facts="test facts"
    )
    assert "第 1 天白天" in task
    assert "Seat1" in task
    assert "观望" in task


def test_speech_task_day2():
    task = build_speech_task(
        player="Seat3", role="werewolf", day=2,
        alive=["Seat1", "Seat3", "Seat5", "Seat7"],
        prior_speeches={"Seat1": "我怀疑Seat3"}, observation="关注Seat5",
        evidence_facts="some facts"
    )
    assert "第 2 天白天" in task
    assert "必须包含怀疑对象" in task
    assert "Seat1" in task
    assert "关注Seat5" in task
    assert "小提示" in task  # werewolf gets hint


def test_first_vote_task():
    task = build_first_vote_task(
        player="Seat1", role="villager", day=1,
        alive=["Seat1", "Seat2", "Seat3"],
        day_summary="GM总结", evidence_facts="facts",
        own_speech="我怀疑Seat3",
    )
    assert "第一轮：初投" in task
    assert "GM总结" in task
    assert "risk_if_wrong" in task


def test_second_vote_task():
    task = build_second_vote_task(
        player="Seat1", role="villager", day=1,
        alive=["Seat1", "Seat2", "Seat3"],
        day_summary="GM总结", vote_distribution="Seat2←Seat1(1票)",
        evidence_facts="facts", consensus_targets=["Seat2"],
        first_vote_target="Seat2", own_speech="我怀疑Seat2",
    )
    assert "第二轮：终投" in task
    assert "changed_vote" in task
    assert "Seat2" in task


def test_summary_task():
    task = build_summary_task(day=1, speeches={"Seat1": "我怀疑Seat3"}, alive=["Seat1", "Seat3"])
    assert "第 1 天" in task
    assert "Seat1" in task
    assert "summary" in task
