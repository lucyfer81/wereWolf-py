from __future__ import annotations

import asyncio
import random
import time as _time
import traceback as _traceback
from pathlib import Path

from src.config_loader import GameConfig, render_template
from src.logger import GameLogger
from src.models import (
    DayProgress,
    GameState,
    Phase,
    PublicEvent,
    SeerResult,
    SpeechRecord,
    VoteRecord,
    WitchState,
    create_new_game_state,
)
from src.llm import PlayerResponse, create_gm_agent, create_player_agent
from src.prompts import (
    build_first_vote_task,
    build_gm_system_prompt,
    build_guard_night_task,
    build_night_task,
    build_player_system_prompt,
    build_second_vote_task,
    build_seer_night_task,
    build_speech_task,
    build_summary_task,
    build_witch_night_task,
    build_wolf_second_round_task,
)
from src.styles import get_style_for_player, get_style_card


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


def _get_player_sys_prompt(state: GameState, player: str, config: GameConfig) -> str:
    style_key = get_style_for_player(player, config)
    style_card = get_style_card(style_key, config)
    role = state.roles[player]
    role_cfg = config.roles[role]

    teammates_in_team = [
        p for p in state.alive_players
        if state.roles[p] == role and p != player
    ]
    role_info = render_template(
        role_cfg.role_info_template, teammates=sorted(teammates_in_team)
    )
    night_action = render_template(role_cfg.night_action_template)

    return build_player_system_prompt(
        config, player, role, role_info,
        style_card["name"], style_card["rules"],
        "\n".join(style_card["scenarios"]),
        night_action,
    )


class WerewolfGame:
    def __init__(self, config: GameConfig, log_dir: Path | None = None):
        self.config = config
        self.state = create_new_game_state(config)
        self._llm_timeout = config.settings.get("llm_timeout", 60)
        self._last_guarded: str | None = None
        self._step_count = 0
        self.log = GameLogger(self.state.game_id, log_dir=log_dir)
        self.log.log(
            "game_start",
            game_id=self.state.game_id,
            roles=dict(self.state.roles),
            alive_players=list(self.state.alive_players),
        )

    async def _call_agent(self, agent, task, player: str = "", role: str = "", model_name: str = "") -> PlayerResponse | None:
        self.log.log(
            "llm_request",
            player=player, role=role, model=model_name,
            system_prompt=getattr(agent, "_system_prompt", "") if isinstance(getattr(agent, "_system_prompt", ""), str) else "",
            task=task,
        )
        start = _time.monotonic()
        try:
            result = await asyncio.wait_for(agent.run(task), timeout=self._llm_timeout)
            elapsed = int((_time.monotonic() - start) * 1000)
            self.log.log(
                "llm_response",
                player=player, role=role, model=model_name,
                response=result.output.model_dump() if hasattr(result.output, "model_dump") else str(result.output),
                elapsed_ms=elapsed, ok=True,
            )
            return result.output
        except asyncio.TimeoutError:
            elapsed = int((_time.monotonic() - start) * 1000)
            self.log.log("llm_timeout", player=player, role=role, model=model_name, elapsed_ms=elapsed)
        except Exception as e:
            elapsed = int((_time.monotonic() - start) * 1000)
            self.log.log("llm_error", player=player, role=role, model=model_name, elapsed_ms=elapsed, error_msg=str(e), traceback=_traceback.format_exc())

        # backup model retry
        start = _time.monotonic()
        try:
            bak_agent = create_player_agent(use_bak=True)
            self.log.log("llm_request", player=player, role=role, model="backup", task=task)
            result = await asyncio.wait_for(bak_agent.run(task), timeout=self._llm_timeout)
            elapsed = int((_time.monotonic() - start) * 1000)
            self.log.log(
                "llm_response",
                player=player, role=role, model="backup",
                response=result.output.model_dump() if hasattr(result.output, "model_dump") else str(result.output),
                elapsed_ms=elapsed, ok=True,
            )
            return result.output
        except asyncio.TimeoutError:
            elapsed = int((_time.monotonic() - start) * 1000)
            self.log.log("llm_timeout", player=player, role=role, model="backup", elapsed_ms=elapsed)
        except Exception as e:
            elapsed = int((_time.monotonic() - start) * 1000)
            self.log.log("llm_error", player=player, role=role, model="backup", elapsed_ms=elapsed, error_msg=str(e), traceback=_traceback.format_exc())
        return None

    async def run_one_step(self) -> GameState:
        if self.state.winner != "none":
            return self.state
        self._step_count += 1
        if self.state.phase == "night":
            self.log.log("phase_start", day=self.state.current_day, phase="night", alive_players=list(self.state.alive_players))
            await self._run_night_phase()
        elif self.state.phase == "day":
            stage = self.state.day_progress.stage
            self.log.log("phase_start", day=self.state.current_day, phase="day", stage=stage, alive_players=list(self.state.alive_players))
            await self._run_day_phase()
        if self.state.winner != "none":
            self.log.log("game_end", winner=self.state.winner, total_steps=self._step_count, alive_players=list(self.state.alive_players))
        return self.state

    async def _run_night_phase(self):
        state = self.state
        config = self.config

        night_roles = sorted(
            [(k, v) for k, v in config.roles.items() if v.night_action],
            key=lambda x: x[1].night_priority,
        )

        night_killed: str | None = None
        guard_protected: str | None = None
        witch_save: str | None = None
        witch_poison: str | None = None

        for role_key, role_cfg in night_roles:
            players_with_role = [
                p for p in state.alive_players if state.roles[p] == role_key
            ]
            if not players_with_role:
                continue

            if role_key == "werewolf":
                wolves = players_with_role

                # --- Round 1: independent votes ---
                round1_votes: dict[str, str] = {}  # wolf -> target
                targets: dict[str, int] = {}
                for wolf in wolves:
                    teammates = [w for w in wolves if w != wolf]
                    task = build_night_task(
                        config, state.current_day, teammates,
                        state.alive_players,
                    )
                    sys_prompt = _get_player_sys_prompt(state, wolf, config)
                    agent = create_player_agent(sys_prompt)
                    resp = await self._call_agent(agent, task, player=wolf, role="werewolf", model_name="primary")
                    if (
                        resp
                        and resp.target in state.alive_players
                        and state.role_teams.get(state.roles.get(resp.target)) != "werewolves"
                    ):
                        round1_votes[wolf] = resp.target
                        targets[resp.target] = targets.get(resp.target, 0) + 1
                        self.log.log("night_action", day=state.current_day, player=wolf, role="werewolf", target=resp.target, round=1)
                    else:
                        self.log.log("fallback", where="werewolf_night_r1", player=wolf, reason="LLM 返回无效目标")
                        non_wolves = [
                            p for p in state.alive_players
                            if state.role_teams.get(state.roles[p]) != "werewolves"
                        ]
                        if non_wolves:
                            t = random.choice(non_wolves)
                            round1_votes[wolf] = t
                            targets[t] = targets.get(t, 0) + 1

                # Check if already majority
                total_wolves = len(wolves)
                majority_target = None
                for t, c in targets.items():
                    if c > total_wolves / 2:
                        majority_target = t
                        break

                if majority_target:
                    night_killed = majority_target
                    self.log.log("night_action", day=state.current_day, player="wolves", role="werewolf", target=night_killed, round=1, result="majority_reached")
                elif targets and total_wolves > 1:
                    # --- Round 2: negotiate with first round results ---
                    first_round_summary = "第一轮投票分布：\n"
                    for target in sort_seats(targets.keys()):
                        voters = [w for w, t in round1_votes.items() if t == target]
                        first_round_summary += f"  {target} ← {', '.join(sort_seats(voters))} ({len(voters)}票)\n"

                    round2_targets: dict[str, int] = {}
                    for wolf in wolves:
                        teammates = [w for w in wolves if w != wolf]
                        task = build_wolf_second_round_task(
                            config, state.current_day, teammates,
                            state.alive_players, first_round_summary,
                        )
                        sys_prompt = _get_player_sys_prompt(state, wolf, config)
                        agent = create_player_agent(sys_prompt)
                        resp = await self._call_agent(agent, task, player=wolf, role="werewolf", model_name="primary")
                        if (
                            resp
                            and resp.target in state.alive_players
                            and state.role_teams.get(state.roles.get(resp.target)) != "werewolves"
                        ):
                            round2_targets[resp.target] = round2_targets.get(resp.target, 0) + 1
                            self.log.log("night_action", day=state.current_day, player=wolf, role="werewolf", target=resp.target, round=2)
                        else:
                            self.log.log("fallback", where="werewolf_night_r2", player=wolf, reason="LLM 返回无效目标")

                    # Resolve round 2: need majority
                    for t, c in round2_targets.items():
                        if c > total_wolves / 2:
                            night_killed = t
                            self.log.log("night_action", day=state.current_day, player="wolves", role="werewolf", target=t, round=2, result="majority_reached")
                            break
                    else:
                        # No majority in round 2: no kill tonight
                        self.log.log("night_action", day=state.current_day, player="wolves", role="werewolf", target="none", round=2, result="no_consensus")
                elif targets:
                    # Only 1 wolf, use their target directly
                    night_killed = list(targets.keys())[0]

            elif role_key == "seer":
                for player in players_with_role:
                    task = build_seer_night_task(
                        config, state.current_day, state.alive_players,
                    )
                    sys_prompt = _get_player_sys_prompt(state, player, config)
                    agent = create_player_agent(sys_prompt)
                    resp = await self._call_agent(agent, task, player=player, role="seer", model_name="primary")
                    if resp and resp.target in state.alive_players:
                        target_role = state.roles[resp.target]
                        team = state.role_teams.get(target_role, "villagers")
                        result = "werewolf" if team == "werewolves" else "good"
                        state.memory.player_memories[player].seer_results.append(
                            SeerResult(
                                day=state.current_day,
                                target=resp.target,
                                result=result,
                            )
                        )
                        self.log.log("night_action", day=state.current_day, player=player, role="seer", target=resp.target, result=result)
                    else:
                        self.log.log("fallback", where="seer_night", player=player, reason="LLM 返回无效目标")

            elif role_key == "guard":
                for player in players_with_role:
                    task = build_guard_night_task(
                        config, state.current_day,
                        state.alive_players, self._last_guarded,
                    )
                    sys_prompt = _get_player_sys_prompt(state, player, config)
                    agent = create_player_agent(sys_prompt)
                    resp = await self._call_agent(agent, task, player=player, role="guard", model_name="primary")
                    if resp and resp.target in state.alive_players:
                        if resp.target != self._last_guarded:
                            guard_protected = resp.target
                            self._last_guarded = resp.target
                            self.log.log("night_action", day=state.current_day, player=player, role="guard", target=resp.target)
                        else:
                            self.log.log("fallback", where="guard_night", player=player, reason="连续守护同一人，无效")
                    else:
                        self._last_guarded = None
                        self.log.log("fallback", where="guard_night", player=player, reason="LLM 返回无效目标")

            elif role_key == "witch":
                for player in players_with_role:
                    if not night_killed:
                        continue
                    pm = state.memory.player_memories[player]
                    if pm.role_state is None:
                        pm.role_state = {
                            "antidote_used": False,
                            "poison_used": False,
                        }
                    ws = pm.role_state
                    task = build_witch_night_task(
                        config, state.current_day, night_killed,
                        state.alive_players,
                        ws["antidote_used"], ws["poison_used"],
                    )
                    sys_prompt = _get_player_sys_prompt(state, player, config)
                    agent = create_player_agent(sys_prompt)
                    resp = await self._call_agent(agent, task, player=player, role="witch", model_name="primary")
                    if resp:
                        if (
                            resp.target == night_killed
                            and not ws["antidote_used"]
                        ):
                            witch_save = night_killed
                            ws["antidote_used"] = True
                            self.log.log("night_action", day=state.current_day, player=player, role="witch", target=resp.target, action="save")
                        elif (
                            resp.target != night_killed
                            and resp.target in state.alive_players
                            and not ws["poison_used"]
                        ):
                            witch_poison = resp.target
                            ws["poison_used"] = True
                            self.log.log("night_action", day=state.current_day, player=player, role="witch", target=resp.target, action="poison")
                    else:
                        self.log.log("fallback", where="witch_night", player=player, reason="LLM 无响应")

        # Resolve deaths
        deaths: list[str] = []
        if night_killed and night_killed != witch_save and night_killed != guard_protected:
            deaths.append(night_killed)
        if witch_poison and witch_poison not in deaths:
            deaths.append(witch_poison)

        for dead in deaths:
            state.alive_players.remove(dead)
            for pm in state.memory.player_memories.values():
                pm.death_log[state.current_day] = dead
            state.timeline.append(
                PublicEvent(
                    day=state.current_day,
                    phase="night",
                    type="death",
                    speaker="GameMaster",
                    content=f"{dead} 被杀害",
                    alive_players=list(state.alive_players),
                )
            )
            self.log.log("death", day=state.current_day, phase="night", player=dead, role=state.roles[dead], cause="killed")

        # Announce peaceful night if no deaths
        if not deaths:
            state.timeline.append(
                PublicEvent(
                    day=state.current_day,
                    phase="night",
                    type="announcement",
                    speaker="GameMaster",
                    content="昨晚是平安夜，无人死亡。",
                    alive_players=list(state.alive_players),
                )
            )
            self.log.log("announcement", day=state.current_day, phase="night", content="peaceful_night")

        # Trigger hunter on-death
        for dead in deaths:
            if state.roles[dead] == "hunter":
                await self._run_hunter_shot(dead)

        # Store werewolf kill
        if night_killed:
            state.memory.werewolf_memory.kills[state.current_day] = night_killed

        winner = state.check_win()
        if winner != "none":
            state.winner = winner
        else:
            state.phase = "day"
            state.day_progress = DayProgress(stage="speeches")

    async def _run_hunter_shot(self, hunter: str):
        """Hunter shoots someone when dying."""
        state = self.state
        config = self.config
        role_cfg = config.roles.get("hunter")
        if not role_cfg or not role_cfg.on_death_template:
            return

        alive = [p for p in state.alive_players if p != hunter]
        if not alive:
            return

        sys_prompt = _get_player_sys_prompt(state, hunter, config)
        agent = create_player_agent(sys_prompt)

        task = render_template(role_cfg.on_death_template)
        task += f"\n当前存活玩家：{', '.join(alive)}"

        resp = await self._call_agent(agent, task, player=hunter, role="hunter", model_name="primary")
        shot_target = None
        if resp and resp.target in alive:
            shot_target = resp.target
        else:
            shot_target = random.choice(alive)

        if shot_target in state.alive_players:
            state.alive_players.remove(shot_target)
            for pm in state.memory.player_memories.values():
                pm.death_log[state.current_day] = shot_target
            state.timeline.append(
                PublicEvent(
                    day=state.current_day,
                    phase="night",
                    type="death",
                    speaker="GameMaster",
                    content=f"{hunter}（猎人）开枪带走了 {shot_target}",
                    alive_players=list(state.alive_players),
                )
            )
            self.log.log("death", day=state.current_day, phase="night", player=shot_target, role=state.roles[shot_target], cause="hunter_shot")
            self.log.log("night_action", day=state.current_day, player=hunter, role="hunter", target=shot_target)

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
        config = self.config
        progress = state.day_progress
        alive = state.sort_alive()

        if progress.speech_index < len(alive):
            player = alive[progress.speech_index]
            sys_prompt = _get_player_sys_prompt(state, player, config)

            evidence_facts = self._build_evidence_facts()
            task = build_speech_task(
                config,
                player=player,
                role=state.roles[player],
                day=state.current_day,
                alive=alive,
                prior_speeches=progress.speeches,
                observation="",
                evidence_facts=evidence_facts,
            )

            agent = create_player_agent(sys_prompt)
            is_fallback = False
            resp = await self._call_agent(agent, task, player=player, role=state.roles[player], model_name="primary")
            if resp:
                err = validate_speech(player, resp.content, resp.target, alive, state.current_day)
                if err:
                    is_fallback = True
                    self.log.log("fallback", where="speech", player=player, reason=err)
                    fb = build_fallback_speech(player, alive, state.current_day)
                    content, target = fb["content"], fb["target"]
                else:
                    content, target = resp.content, resp.target
            else:
                is_fallback = True
                self.log.log("fallback", where="speech", player=player, reason="LLM 无响应")
                fb = build_fallback_speech(player, alive, state.current_day)
                content, target = fb["content"], fb["target"]

            progress.speeches[player] = content
            state.memory.player_memories[player].speech_log.setdefault(
                state.current_day, []
            ).append(SpeechRecord(speaker=player, content=content, target=target))

            self.log.log("speech", day=state.current_day, player=player, role=state.roles[player], content=content, target=target, is_fallback=is_fallback)

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
        config = self.config

        sys_prompt = build_gm_system_prompt(config)
        agent = create_gm_agent(sys_prompt)
        task = build_summary_task(
            config, state.current_day, state.day_progress.speeches, state.sort_alive()
        )
        try:
            result = await asyncio.wait_for(agent.run(task), timeout=self._llm_timeout)
            summary = result.output.summary
        except Exception:
            self.log.log("fallback", where="summary", player="GM", reason="GM 摘要生成失败")
            summary = f"第{state.current_day}天：玩家们进行了讨论。"

        state.day_progress.day_summary = summary
        self.log.log("summary", day=state.current_day, content=summary)
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
        config = self.config
        alive = state.sort_alive()

        for player in alive:
            sys_prompt = _get_player_sys_prompt(state, player, config)
            evidence_facts = self._build_evidence_facts()
            own_speech = state.day_progress.speeches.get(player, "（无）")
            task = build_first_vote_task(
                config,
                player=player,
                role=state.roles[player],
                day=state.current_day,
                alive=alive,
                day_summary=state.day_progress.day_summary,
                evidence_facts=evidence_facts,
                own_speech=own_speech,
            )

            agent = create_player_agent(sys_prompt)
            resp = await self._call_agent(agent, task, player=player, role=state.roles[player], model_name="primary")
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
                self.log.log("vote", day=state.current_day, player=player, role=state.roles[player], round="first", target=resp.target, alt_target=resp.alt_target, evidence=resp.evidence, changed_vote=False, is_fallback=False)
            else:
                self.log.log("fallback", where="first_vote", player=player, reason="LLM 返回无效投票")
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
                self.log.log("vote", day=state.current_day, player=player, role=state.roles[player], round="first", target=fb["target"], alt_target=fb["alt_target"], evidence=fb["evidence"], changed_vote=False, is_fallback=True)

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
        config = self.config
        alive = state.sort_alive()

        for player in alive:
            sys_prompt = _get_player_sys_prompt(state, player, config)
            evidence_facts = self._build_evidence_facts()
            own_speech = state.day_progress.speeches.get(player, "（无）")
            first_target = state.day_progress.initial_votes.get(player, player)
            task = build_second_vote_task(
                config,
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
            resp = await self._call_agent(agent, task, player=player, role=state.roles[player], model_name="primary")
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
                self.log.log("vote", day=state.current_day, player=player, role=state.roles[player], round="second", target=resp.target, alt_target=resp.alt_target, evidence=resp.evidence, changed_vote=changed, why_change=resp.why_change if changed else "", is_fallback=False)
            else:
                self.log.log("fallback", where="second_vote", player=player, reason="LLM 返回无效投票")
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
                self.log.log("vote", day=state.current_day, player=player, role=state.roles[player], round="second", target=fb["target"], alt_target=fb["alt_target"], evidence=fb["evidence"], changed_vote=False, is_fallback=True)

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
                self.log.log("death", day=state.current_day, phase="day", player=eliminated, role=state.roles[eliminated], cause="voted", votes=max_votes)
                self.log.log("phase_end", day=state.current_day, phase="day", stage="resolve", eliminated=eliminated)

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
