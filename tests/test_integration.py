from __future__ import annotations

from pathlib import Path

import pytest
from unittest.mock import AsyncMock, patch

from src.config_loader import load_config
from src.game import WerewolfGame
from src.llm import PlayerResponse, GMSummary

FIXTURE_DIR = Path(__file__).parent / "fixtures"


def _resp(target: str, content: str, action: str = "speech", **kw) -> PlayerResponse:
    return PlayerResponse(
        action=action,
        target=target,
        content=content,
        confidence=kw.get("confidence", "medium"),
        risk_if_wrong=kw.get("risk_if_wrong", "投错可能误杀村民"),
        alt_target=kw.get("alt_target", "Seat1"),
        target_vs_alt_reason=kw.get(
            "reason", "该玩家行为更可疑一些，值得重点关注"
        ),
        evidence=kw.get("evidence", ["基于发言判断"]),
        changed_vote=False,
        why_change="",
    )


class _MockResult:
    def __init__(self, output):
        self.output = output


@pytest.mark.asyncio
async def test_full_game_with_mock():
    config = load_config(FIXTURE_DIR / "default-8p.yaml")
    game = WerewolfGame(config)
    call_count = 0

    async def mock_run(prompt, **kwargs):
        nonlocal call_count
        call_count += 1
        prompt_str = str(prompt)

        if "夜晚" in prompt_str:
            villagers = [
                p for p in game.state.alive_players if game.state.role_teams.get(game.state.roles[p]) == "villagers"
            ]
            target = villagers[0] if villagers else "Seat1"
            return _MockResult(_resp(target, f"选择击杀{target}", action="night_action"))

        if "终投" in prompt_str or "初投" in prompt_str:
            alive = game.state.sort_alive()
            wolves_alive = [
                p for p in alive if game.state.role_teams.get(game.state.roles[p]) == "werewolves"
            ]
            target = wolves_alive[0] if wolves_alive else alive[0]
            others = [p for p in alive if p != target]
            alt = others[0] if others else alive[0]
            return _MockResult(
                _resp(target, f"投{target}", action="vote", alt_target=alt)
            )

        if "发言" in prompt_str or "白天" in prompt_str:
            alive = game.state.sort_alive()
            others = [p for p in alive if p != "Seat1"]
            target = others[0] if others else alive[0]
            return _MockResult(
                _resp(target, f"我怀疑{target}的行为", action="speech")
            )

        return _MockResult(GMSummary(summary="玩家们进行了讨论，提出了各自的怀疑。"))

    mock_agent = AsyncMock()
    mock_agent.run = mock_run

    with (
        patch("src.game.create_player_agent", return_value=mock_agent),
        patch("src.game.create_gm_agent", return_value=mock_agent),
    ):
        steps = 0
        while game.state.winner == "none" and steps < 100:
            await game.run_one_step()
            steps += 1

    assert game.state.winner in ("werewolves", "villagers")
    assert steps < 100
    assert len(game.state.timeline) > 0
    assert call_count > 0


@pytest.mark.asyncio
async def test_night_then_day_phase_transition():
    config = load_config(FIXTURE_DIR / "default-8p.yaml")
    game = WerewolfGame(config)

    async def mock_run(prompt, **kwargs):
        if "夜晚" in str(prompt):
            villagers = [
                p for p in game.state.alive_players if game.state.role_teams.get(game.state.roles[p]) == "villagers"
            ]
            return _MockResult(
                _resp(villagers[0], "kill", action="night_action")
            )
        if "发言" in str(prompt) or "白天" in str(prompt):
            alive = game.state.sort_alive()
            others = [p for p in alive if p != "Seat1"]
            return _MockResult(
                _resp(others[0] if others else alive[0], "speech", action="speech")
            )
        return _MockResult(GMSummary(summary="summary"))

    mock_agent = AsyncMock()
    mock_agent.run = mock_run

    with (
        patch("src.game.create_player_agent", return_value=mock_agent),
        patch("src.game.create_gm_agent", return_value=mock_agent),
    ):
        # Night phase
        assert game.state.phase == "night"
        await game.run_one_step()
        assert game.state.phase == "day"
        assert game.state.day_progress.stage == "speeches"


@pytest.mark.asyncio
async def test_full_9p_game_with_mock():
    config = load_config(FIXTURE_DIR / "classic-9p.yaml")
    game = WerewolfGame(config)

    async def mock_run(prompt, **kwargs):
        prompt_str = str(prompt)

        if "夜晚" in prompt_str or "查验" in prompt_str or "毒药" in prompt_str or "解药" in prompt_str or "被杀" in prompt_str:
            # For any night action, target a non-wolf player
            non_wolves = [
                p for p in game.state.alive_players
                if game.state.role_teams.get(game.state.roles[p]) != "werewolves"
            ]
            target = non_wolves[0] if non_wolves else "Seat1"
            return _MockResult(_resp(target, f"行动{target}", action="night_action"))

        if "终投" in prompt_str or "初投" in prompt_str:
            alive = game.state.sort_alive()
            wolves_alive = [
                p for p in alive if game.state.role_teams.get(game.state.roles[p]) == "werewolves"
            ]
            target = wolves_alive[0] if wolves_alive else alive[0]
            others = [p for p in alive if p != target]
            alt = others[0] if others else alive[0]
            return _MockResult(
                _resp(target, f"投{target}", action="vote", alt_target=alt)
            )

        if "发言" in prompt_str or "白天" in prompt_str:
            alive = game.state.sort_alive()
            others = [p for p in alive if p != "Seat1"]
            target = others[0] if others else alive[0]
            return _MockResult(
                _resp(target, f"我怀疑{target}", action="speech")
            )

        if "淘汰" in prompt_str or "开枪" in prompt_str:
            # Hunter shot - target a wolf
            alive = game.state.sort_alive()
            wolves_alive = [
                p for p in alive if game.state.role_teams.get(game.state.roles[p]) == "werewolves"
            ]
            target = wolves_alive[0] if wolves_alive else (alive[0] if alive else "Seat1")
            return _MockResult(_resp(target, f"开枪{target}", action="night_action"))

        return _MockResult(GMSummary(summary="讨论摘要"))

    mock_agent = AsyncMock()
    mock_agent.run = mock_run

    with (
        patch("src.game.create_player_agent", return_value=mock_agent),
        patch("src.game.create_gm_agent", return_value=mock_agent),
    ):
        steps = 0
        while game.state.winner == "none" and steps < 200:
            await game.run_one_step()
            steps += 1

    assert game.state.winner in ("werewolves", "villagers")
    assert steps < 200


@pytest.mark.asyncio
async def test_memory_tracks_events():
    config = load_config(FIXTURE_DIR / "default-8p.yaml")
    game = WerewolfGame(config)
    wolves = [p for p in game.state.roles if game.state.role_teams.get(game.state.roles[p]) == "werewolves"]

    async def mock_run(prompt, **kwargs):
        if "夜晚" in str(prompt):
            villagers = [
                p for p in game.state.alive_players if game.state.role_teams.get(game.state.roles[p]) == "villagers"
            ]
            return _MockResult(_resp(villagers[0], "kill", action="night_action"))
        if "发言" in str(prompt) or "白天" in str(prompt):
            alive = game.state.sort_alive()
            return _MockResult(_resp(alive[-1], "speech", action="speech"))
        return _MockResult(GMSummary(summary="summary"))

    mock_agent = AsyncMock()
    mock_agent.run = mock_run

    with (
        patch("src.game.create_player_agent", return_value=mock_agent),
        patch("src.game.create_gm_agent", return_value=mock_agent),
    ):
        # Run night
        await game.run_one_step()
        # Check death was tracked in memory (or peaceful night announced)
        death_events = [e for e in game.state.timeline if e.type == "death"]
        if death_events:
            assert len(death_events) == 1
            # Check player memories have death logged
            for pm in game.state.memory.player_memories.values():
                assert 1 in pm.death_log
        else:
            # Peaceful night: should have an announcement
            announcement_events = [e for e in game.state.timeline if e.type == "announcement"]
            assert len(announcement_events) >= 1


@pytest.mark.asyncio
async def test_wolf_two_round_voting():
    """Wolves do two rounds of voting when no majority in round 1."""
    config = load_config(FIXTURE_DIR / "default-8p.yaml")
    game = WerewolfGame(config)
    r1_count = 0
    r2_count = 0

    async def mock_run(prompt, **kwargs):
        nonlocal r1_count, r2_count
        prompt_str = str(prompt)

        if "第二轮" in prompt_str:
            r2_count += 1
            # All wolves agree on first non-wolf in round 2
            non_wolves = [p for p in game.state.alive_players if game.state.role_teams.get(game.state.roles[p]) != "werewolves"]
            return _MockResult(_resp(non_wolves[0], "r2 consensus", action="night_action"))

        if "击杀" in prompt_str or "杀目标" in prompt_str:
            # Wolf round 1 prompt contains "击杀目标"
            r1_count += 1
            # Each wolf picks a different target in round 1
            non_wolves = [p for p in game.state.alive_players if game.state.role_teams.get(game.state.roles[p]) != "werewolves"]
            idx = (r1_count - 1) % len(non_wolves)
            return _MockResult(_resp(non_wolves[idx], f"r1 split", action="night_action"))

        if "查验" in prompt_str:
            # Seer night action - target a wolf
            wolves = [p for p in game.state.alive_players if game.state.role_teams.get(game.state.roles[p]) == "werewolves"]
            target = wolves[0] if wolves else game.state.alive_players[0]
            return _MockResult(_resp(target, "seer check", action="night_action"))

        if "守护" in prompt_str:
            # Guard protects a wolf (not the wolf kill target) so guard doesn't block
            wolves = [p for p in game.state.alive_players if game.state.role_teams.get(game.state.roles[p]) == "werewolves"]
            return _MockResult(_resp(wolves[0], "guard a wolf", action="night_action"))

        if "终投" in prompt_str or "初投" in prompt_str:
            alive = game.state.sort_alive()
            wolves_alive = [p for p in alive if game.state.role_teams.get(game.state.roles[p]) == "werewolves"]
            target = wolves_alive[0] if wolves_alive else alive[0]
            others = [p for p in alive if p != target]
            alt = others[0] if others else alive[0]
            return _MockResult(_resp(target, f"投{target}", action="vote", alt_target=alt))

        if "发言" in prompt_str or "白天" in prompt_str:
            alive = game.state.sort_alive()
            others = [p for p in alive if p != "Seat1"]
            target = others[0] if others else alive[0]
            return _MockResult(_resp(target, f"speech", action="speech"))

        return _MockResult(GMSummary(summary="summary"))

    mock_agent = AsyncMock()
    mock_agent.run = mock_run

    with (
        patch("src.game.create_player_agent", return_value=mock_agent),
        patch("src.game.create_gm_agent", return_value=mock_agent),
    ):
        await game.run_one_step()  # night

    # Round 1: 3 wolf calls. Round 2: 3 wolf calls (because 3 wolves split in r1).
    assert r1_count == 3
    assert r2_count == 3
    # Someone should have been killed (wolves agreed in round 2)
    death_events = [e for e in game.state.timeline if e.type == "death"]
    assert len(death_events) == 1


@pytest.mark.asyncio
async def test_peaceful_night_announcement():
    """When no one dies at night, a peaceful night announcement appears."""
    config = load_config(FIXTURE_DIR / "default-8p.yaml")
    game = WerewolfGame(config)
    call_idx = 0

    async def mock_run(prompt, **kwargs):
        nonlocal call_idx
        call_idx += 1
        prompt_str = str(prompt)

        if "第二轮" in prompt_str:
            # Wolves still disagree in round 2 - each picks different target
            non_wolves = [p for p in game.state.alive_players if game.state.role_teams.get(game.state.roles[p]) != "werewolves"]
            idx = call_idx % len(non_wolves)
            return _MockResult(_resp(non_wolves[idx], "still disagree", action="night_action"))

        if "击杀" in prompt_str or "杀目标" in prompt_str:
            # Wolf round 1 - each wolf picks a different target
            non_wolves = [p for p in game.state.alive_players if game.state.role_teams.get(game.state.roles[p]) != "werewolves"]
            idx = call_idx % len(non_wolves)
            return _MockResult(_resp(non_wolves[idx], "kill", action="night_action"))

        if "查验" in prompt_str or "守护" in prompt_str:
            # Seer or guard night action
            non_wolves = [p for p in game.state.alive_players if game.state.role_teams.get(game.state.roles[p]) != "werewolves"]
            return _MockResult(_resp(non_wolves[0], "night action", action="night_action"))

        if "终投" in prompt_str or "初投" in prompt_str:
            alive = game.state.sort_alive()
            return _MockResult(_resp(alive[0], "vote", action="vote", alt_target=alive[1]))
        if "发言" in prompt_str or "白天" in prompt_str:
            alive = game.state.sort_alive()
            return _MockResult(_resp(alive[-1], "speech", action="speech"))
        return _MockResult(GMSummary(summary="summary"))

    mock_agent = AsyncMock()
    mock_agent.run = mock_run

    with (
        patch("src.game.create_player_agent", return_value=mock_agent),
        patch("src.game.create_gm_agent", return_value=mock_agent),
    ):
        await game.run_one_step()  # night

    # Should have a peaceful night announcement
    announcements = [e for e in game.state.timeline if e.type == "announcement"]
    assert len(announcements) == 1
    assert "平安夜" in announcements[0].content
