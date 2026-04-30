from __future__ import annotations

import asyncio
import random

from src.models import (
    DayProgress,
    GameState,
    Phase,
    PublicEvent,
    SpeechRecord,
    VoteRecord,
    create_new_game_state,
)
from src.llm import PlayerResponse, create_gm_agent, create_player_agent
from src.prompts import (
    build_first_vote_task,
    build_night_task,
    build_player_system_prompt,
    build_second_vote_task,
    build_speech_task,
    build_summary_task,
)
from src.styles import VOTING_STYLE_CARDS, get_style_for_player

LLM_TIMEOUT = 60


def sort_seats(seats: list[str]) -> list[str]:
    return sorted(seats, key=lambda s: int(s.replace("Seat", "")))


def validate_speech(
    player: str, content: str, target: str, alive: list[str], day: int
) -> str | None:
    if not content.strip():
        return "发言内容为空"
    if day > 1:
        if not target or not target.startswith("Seat"):
            return "缺少有效怀疑目标 target"
        if target not in alive:
            return "怀疑目标不是存活玩家"
        if target == player:
            return "怀疑目标不能是自己"
    for hint in ("我怀疑自己", "我是狼", "我觉得自己像狼"):
        if hint in content:
            return "发言内容包含自我怀疑"
    return None


def validate_vote(
    player: str, target: str, alt_target: str, alive: list[str], **kwargs
) -> str | None:
    if target not in alive:
        return "target 不是存活玩家"
    if not alt_target or alt_target not in alive:
        return "alt_target 不是存活玩家"
    if alt_target == target:
        return "alt_target 必须与 target 不同"
    if alt_target == player:
        return "alt_target 不能是你自己"
    return None


def build_fallback_speech(player: str, alive: list[str], day: int) -> dict:
    others = [p for p in alive if p != player]
    target = random.choice(others) if others else player
    if day == 1:
        return {
            "target": target,
            "content": f"第一天信息有限，我先观望，但会重点关注 {target} 后续发言与投票是否一致。",
        }
    return {
        "target": target,
        "content": f"我暂时怀疑 {target}，其发言与投票逻辑存在跳跃，我会继续观察后续一致性。",
    }


def build_fallback_vote(player: str, alive: list[str]) -> dict:
    others = [p for p in alive if p != player]
    alt = random.choice(others) if others else player
    return {
        "target": player,
        "confidence": "low",
        "risk_if_wrong": "证据不足时强行站队可能误杀村民并暴露推理漏洞。",
        "alt_target": alt,
        "target_vs_alt_reason": "当前证据不足以判断，先保守观望。",
        "evidence": ["证据不足，保守处理。", "避免在信息不充分时跟票。"],
        "changed_vote": False,
        "why_change": "",
    }


def _get_player_sys_prompt(state: GameState, player: str) -> str:
    style_key = get_style_for_player(player)
    style_card = VOTING_STYLE_CARDS[style_key]
    role = state.roles[player]
    wolves = [p for p in state.alive_players if state.roles[p] == "werewolf"]

    if role == "werewolf":
        teammates = [w for w in wolves if w != player]
        role_info = f"你是狼人。你的同伴是：{', '.join(sorted(teammates)) or '（无）'}"
        night_action = "夜晚时，与同伴商议并选择一个村民进行击杀。"
    else:
        role_info = "你是村民。你不知道其他任何人的身份。"
        night_action = "夜晚时，村民没有行动，请等待天亮。"

    return build_player_system_prompt(
        player, role, role_info,
        style_card["name"], style_card["rules"],
        "\n".join(style_card["scenarios"]),
        night_action,
    )


class WerewolfGame:
    def __init__(self):
        self.state = create_new_game_state()

    async def _call_agent(self, agent, task) -> PlayerResponse | None:
        try:
            result = await asyncio.wait_for(agent.run(task), timeout=LLM_TIMEOUT)
            return result.output
        except Exception:
            pass
        try:
            bak_agent = create_player_agent(use_bak=True)
            result = await asyncio.wait_for(bak_agent.run(task), timeout=LLM_TIMEOUT)
            return result.output
        except Exception:
            return None

    async def run_one_step(self) -> GameState:
        if self.state.winner != "none":
            return self.state
        if self.state.phase == "night":
            await self._run_night_phase()
        elif self.state.phase == "day":
            await self._run_day_phase()
        return self.state

    async def _run_night_phase(self):
        state = self.state
        wolves = [p for p in state.alive_players if state.roles[p] == "werewolf"]

        if not wolves:
            state.winner = state.check_win()
            state.phase = "day"
            return

        targets: dict[str, int] = {}

        for wolf in wolves:
            teammates = [w for w in wolves if w != wolf]
            observation = ""
            task = build_night_task(state.current_day, teammates, state.alive_players, observation)
            sys_prompt = _get_player_sys_prompt(state, wolf)
            agent = create_player_agent(sys_prompt)

            resp = await self._call_agent(agent, task)
            if resp and resp.target in state.alive_players and state.roles.get(resp.target) != "werewolf":
                targets[resp.target] = targets.get(resp.target, 0) + 1
            else:
                villagers = [p for p in state.alive_players if state.roles[p] == "villager"]
                if villagers:
                    t = random.choice(villagers)
                    targets[t] = targets.get(t, 0) + 1

        if targets:
            max_votes = max(targets.values())
            top_targets = [t for t, c in targets.items() if c == max_votes]
            kill_target = sort_seats(top_targets)[0]

            state.alive_players.remove(kill_target)
            state.memory.werewolf_memory.kills[state.current_day] = kill_target

            state.timeline.append(
                PublicEvent(
                    day=state.current_day,
                    phase="night",
                    type="death",
                    speaker="GameMaster",
                    content=f"{kill_target} 被狼人杀害",
                    alive_players=list(state.alive_players),
                )
            )
            for pm in state.memory.player_memories.values():
                pm.death_log[state.current_day] = kill_target

        winner = state.check_win()
        if winner != "none":
            state.winner = winner
        else:
            state.phase = "day"
            state.day_progress = DayProgress(stage="speeches")

    async def _run_day_phase(self):
        state = self.state
        progress = state.day_progress

        if progress.stage == "speeches":
            await self._run_speeches()
        elif progress.stage == "summary":
            await self._run_summary()
        elif progress.stage == "first_vote":
            await self._run_first_vote()
        elif progress.stage == "second_vote":
            await self._run_second_vote()
        elif progress.stage == "resolve":
            await self._run_resolve()

    async def _run_speeches(self):
        state = self.state
        progress = state.day_progress
        alive = state.sort_alive()

        if progress.speech_index < len(alive):
            player = alive[progress.speech_index]
            sys_prompt = _get_player_sys_prompt(state, player)

            evidence_facts = self._build_evidence_facts()
            task = build_speech_task(
                player=player,
                role=state.roles[player],
                day=state.current_day,
                alive=alive,
                prior_speeches=progress.speeches,
                observation="",
                evidence_facts=evidence_facts,
            )

            agent = create_player_agent(sys_prompt)
            resp = await self._call_agent(agent, task)
            if resp:
                err = validate_speech(player, resp.content, resp.target, alive, state.current_day)
                if err:
                    fb = build_fallback_speech(player, alive, state.current_day)
                    content, target = fb["content"], fb["target"]
                else:
                    content, target = resp.content, resp.target
            else:
                fb = build_fallback_speech(player, alive, state.current_day)
                content, target = fb["content"], fb["target"]

            progress.speeches[player] = content
            state.memory.player_memories[player].speech_log.setdefault(
                state.current_day, []
            ).append(SpeechRecord(speaker=player, content=content, target=target))

            state.timeline.append(
                PublicEvent(
                    day=state.current_day,
                    phase="day",
                    type="speech",
                    speaker=player,
                    content=content,
                    alive_players=list(alive),
                )
            )
            progress.speech_index += 1

        if progress.speech_index >= len(alive):
            progress.stage = "summary"

    async def _run_summary(self):
        state = self.state

        from src.prompts import build_gm_system_prompt

        sys_prompt = build_gm_system_prompt()
        agent = create_gm_agent(sys_prompt)
        task = build_summary_task(
            state.current_day, state.day_progress.speeches, state.sort_alive()
        )
        try:
            result = await asyncio.wait_for(agent.run(task), timeout=LLM_TIMEOUT)
            summary = result.output.summary
        except Exception:
            summary = f"第{state.current_day}天：玩家们进行了讨论。"

        state.day_progress.day_summary = summary
        state.timeline.append(
            PublicEvent(
                day=state.current_day,
                phase="day",
                type="summary",
                speaker="GameMaster",
                content=summary,
                alive_players=list(state.alive_players),
            )
        )
        state.day_progress.stage = "first_vote"

    async def _run_first_vote(self):
        state = self.state
        alive = state.sort_alive()

        for player in alive:
            sys_prompt = _get_player_sys_prompt(state, player)
            evidence_facts = self._build_evidence_facts()
            own_speech = state.day_progress.speeches.get(player, "（无）")
            task = build_first_vote_task(
                player=player,
                role=state.roles[player],
                day=state.current_day,
                alive=alive,
                day_summary=state.day_progress.day_summary,
                evidence_facts=evidence_facts,
                own_speech=own_speech,
            )

            agent = create_player_agent(sys_prompt)
            resp = await self._call_agent(agent, task)
            if resp and not validate_vote(player, resp.target, resp.alt_target, alive):
                state.day_progress.initial_votes[player] = resp.target
                vr = VoteRecord(
                    voter=player,
                    target=resp.target,
                    alt_target=resp.alt_target,
                    confidence=resp.confidence,
                    risk_if_wrong=resp.risk_if_wrong,
                    target_vs_alt_reason=resp.target_vs_alt_reason,
                    evidence=resp.evidence,
                )
            else:
                fb = build_fallback_vote(player, alive)
                state.day_progress.initial_votes[player] = fb["target"]
                vr = VoteRecord(
                    voter=player,
                    target=fb["target"],
                    alt_target=fb["alt_target"],
                    confidence=fb["confidence"],
                    risk_if_wrong=fb["risk_if_wrong"],
                    target_vs_alt_reason=fb["target_vs_alt_reason"],
                    evidence=fb["evidence"],
                )

            state.memory.player_memories[player].vote_log.setdefault(
                state.current_day, []
            ).append(vr)

        state.day_progress.vote_distribution = self._build_vote_distribution(
            state.day_progress.initial_votes
        )
        state.day_progress.consensus_targets = self._get_consensus_targets(
            state.day_progress.initial_votes
        )
        state.day_progress.stage = "second_vote"

    async def _run_second_vote(self):
        state = self.state
        alive = state.sort_alive()

        for player in alive:
            sys_prompt = _get_player_sys_prompt(state, player)
            evidence_facts = self._build_evidence_facts()
            own_speech = state.day_progress.speeches.get(player, "（无）")
            first_target = state.day_progress.initial_votes.get(player, player)
            task = build_second_vote_task(
                player=player,
                role=state.roles[player],
                day=state.current_day,
                alive=alive,
                day_summary=state.day_progress.day_summary,
                vote_distribution=state.day_progress.vote_distribution,
                evidence_facts=evidence_facts,
                consensus_targets=state.day_progress.consensus_targets,
                first_vote_target=first_target,
                own_speech=own_speech,
            )

            agent = create_player_agent(sys_prompt)
            resp = await self._call_agent(agent, task)
            if resp and not validate_vote(player, resp.target, resp.alt_target, alive):
                changed = resp.changed_vote and len(resp.why_change) >= 5
                vr = VoteRecord(
                    voter=player,
                    target=resp.target,
                    alt_target=resp.alt_target,
                    confidence=resp.confidence,
                    risk_if_wrong=resp.risk_if_wrong,
                    target_vs_alt_reason=resp.target_vs_alt_reason,
                    evidence=resp.evidence,
                    changed_vote=changed,
                    why_change=resp.why_change if changed else "",
                )
            else:
                fb = build_fallback_vote(player, alive)
                vr = VoteRecord(
                    voter=player,
                    target=fb["target"],
                    alt_target=fb["alt_target"],
                    confidence=fb["confidence"],
                    risk_if_wrong=fb["risk_if_wrong"],
                    target_vs_alt_reason=fb["target_vs_alt_reason"],
                    evidence=fb["evidence"],
                )

            state.day_progress.final_votes[player] = vr
            state.memory.player_memories[player].vote_log.setdefault(
                state.current_day, []
            ).append(vr)

        state.day_progress.stage = "resolve"

    async def _run_resolve(self):
        state = self.state
        vote_counts: dict[str, int] = {}
        for vr in state.day_progress.final_votes.values():
            vote_counts[vr.target] = vote_counts.get(vr.target, 0) + 1

        if vote_counts:
            max_votes = max(vote_counts.values())
            top = [p for p, c in vote_counts.items() if c == max_votes]
            if len(top) == 1:
                eliminated = top[0]
                state.alive_players.remove(eliminated)
                for pm in state.memory.player_memories.values():
                    pm.death_log[state.current_day] = eliminated
                state.timeline.append(
                    PublicEvent(
                        day=state.current_day,
                        phase="day",
                        type="death",
                        speaker="GameMaster",
                        content=f"{eliminated} 被投票处决（{max_votes}票）",
                        alive_players=list(state.alive_players),
                    )
                )

        winner = state.check_win()
        if winner != "none":
            state.winner = winner
        else:
            state.current_day += 1
            state.phase = "night"
            state.day_progress = DayProgress()

    def _build_evidence_facts(self) -> str:
        parts: list[str] = []
        for event in self.state.timeline:
            if event.type in ("speech", "vote", "summary", "death"):
                parts.append(
                    f"[Day{event.day} {event.phase}] {event.speaker}: {event.content}"
                )
        return "\n".join(parts)

    def _build_vote_distribution(self, votes: dict[str, str]) -> str:
        counts: dict[str, list[str]] = {}
        for voter, target in votes.items():
            counts.setdefault(target, []).append(voter)
        lines = ["第一轮投票分布："]
        for target in sort_seats(counts.keys()):
            lines.append(
                f"  {target} ← {', '.join(sort_seats(counts[target]))} ({len(counts[target])}票)"
            )
        return "\n".join(lines)

    def _get_consensus_targets(self, votes: dict[str, str]) -> list[str]:
        if not votes:
            return []
        counts: dict[str, int] = {}
        for target in votes.values():
            counts[target] = counts.get(target, 0) + 1
        if not counts:
            return []
        max_v = max(counts.values())
        return sort_seats([t for t, c in counts.items() if c == max_v])
