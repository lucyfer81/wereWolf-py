from __future__ import annotations

import pytest
from unittest.mock import AsyncMock, patch

from src.game import WerewolfGame
from src.llm import PlayerResponse, GMSummary


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
    game = WerewolfGame()
    call_count = 0

    async def mock_run(prompt, **kwargs):
        nonlocal call_count
        call_count += 1
        prompt_str = str(prompt)

        if "夜晚" in prompt_str:
            villagers = [
                p for p in game.state.alive_players if game.state.roles[p] == "villager"
            ]
            target = villagers[0] if villagers else "Seat1"
            return _MockResult(_resp(target, f"选择击杀{target}", action="night_action"))

        if "终投" in prompt_str or "初投" in prompt_str:
            alive = game.state.sort_alive()
            wolves_alive = [
                p for p in alive if game.state.roles[p] == "werewolf"
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
    game = WerewolfGame()

    async def mock_run(prompt, **kwargs):
        if "夜晚" in str(prompt):
            villagers = [
                p for p in game.state.alive_players if game.state.roles[p] == "villager"
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
async def test_memory_tracks_events():
    game = WerewolfGame()
    wolves = [p for p in game.state.roles if game.state.roles[p] == "werewolf"]

    async def mock_run(prompt, **kwargs):
        if "夜晚" in str(prompt):
            villagers = [
                p for p in game.state.alive_players if game.state.roles[p] == "villager"
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
        # Check death was tracked in memory
        if game.state.timeline:
            death_events = [e for e in game.state.timeline if e.type == "death"]
            assert len(death_events) == 1
            # Check player memories have death logged
            for pm in game.state.memory.player_memories.values():
                assert 1 in pm.death_log
