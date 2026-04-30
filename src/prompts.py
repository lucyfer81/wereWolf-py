from __future__ import annotations

import json

from src.config_loader import GameConfig, render_template


def build_player_system_prompt(
    config: GameConfig,
    player_name: str,
    role: str,
    role_info: str,
    style_name: str,
    style_rules: str,
    style_scenarios: str,
    night_action: str,
) -> str:
    sections = [
        render_template(
            config.prompts["system_header"],
            total_players=config.total_players,
            wolf_count=sum(1 for r in config.roles.values() if r.team == "werewolves"),
            player_name=player_name,
            role=role,
            role_info=role_info,
            player_range=f"Seat1 - Seat{config.total_players}",
        ),
        render_template(
            config.prompts["voting_style"],
            style_name=style_name,
            style_rules=style_rules,
            style_scenarios=style_scenarios,
        ),
        render_template(
            config.prompts["unknown_info"],
            player_name=player_name,
        ),
        render_template(
            config.prompts["night_action_section"],
            night_action=night_action,
        ),
        render_template(
            config.prompts["output_format"],
            allowed_actions=["speech", "vote", "night_action"],
            player_names=[f"Seat{i+1}" for i in range(config.total_players)],
        ),
    ]
    return "\n".join(sections)


def build_gm_system_prompt(config: GameConfig) -> str:
    return render_template(config.prompts["gm_system"])


def build_night_task(
    config: GameConfig,
    day: int,
    teammates: list[str],
    alive_players: list[str],
    observation: str = "",
) -> str:
    return render_template(
        config.prompts["night_task"],
        day=day,
        role_specific_night_instruction=f"你是狼人。你的同伴：{', '.join(teammates) or '（无）'}",
        alive_players=alive_players,
        night_verb="击杀目标",
        night_task_hint=config.roles["werewolf"].night_task_hint,
        observation=observation,
    )


def build_seer_night_task(
    config: GameConfig,
    day: int,
    alive_players: list[str],
) -> str:
    return render_template(
        config.prompts.get("seer_night_task", ""),
        day=day,
        alive_players=alive_players,
    )


def build_witch_night_task(
    config: GameConfig,
    day: int,
    killed_player: str,
    alive_players: list[str],
    antidote_used: bool,
    poison_used: bool,
) -> str:
    return render_template(
        config.prompts.get("witch_night_task", ""),
        day=day,
        killed_player=killed_player,
        alive_players=alive_players,
        antidote_used=antidote_used,
        poison_used=poison_used,
    )


def build_speech_task(
    config: GameConfig,
    player: str,
    role: str,
    day: int,
    alive: list[str],
    prior_speeches: dict[str, str],
    observation: str,
    evidence_facts: str,
) -> str:
    return render_template(
        config.prompts["speech_task"],
        day=day,
        player=player,
        role=role,
        alive=alive,
        prior_speeches=prior_speeches,
        prior_speeches_json=json.dumps(prior_speeches, ensure_ascii=False, indent=2) if prior_speeches else "",
        observation=observation,
        evidence_facts=evidence_facts,
    )


def build_first_vote_task(
    config: GameConfig,
    player: str,
    role: str,
    day: int,
    alive: list[str],
    day_summary: str,
    evidence_facts: str,
    own_speech: str,
    observation: str = "",
    recent_death: str = "",
) -> str:
    return render_template(
        config.prompts["first_vote_task"],
        day=day,
        player=player,
        role=role,
        alive=alive,
        day_summary=day_summary,
        evidence_facts=evidence_facts,
        own_speech=own_speech,
        observation=observation,
        recent_death=recent_death,
    )


def build_second_vote_task(
    config: GameConfig,
    player: str,
    role: str,
    day: int,
    alive: list[str],
    day_summary: str,
    vote_distribution: str,
    evidence_facts: str,
    consensus_targets: list[str],
    first_vote_target: str,
    own_speech: str,
    observation: str = "",
    recent_death: str = "",
) -> str:
    return render_template(
        config.prompts["second_vote_task"],
        day=day,
        player=player,
        role=role,
        alive=alive,
        day_summary=day_summary,
        vote_distribution=vote_distribution,
        evidence_facts=evidence_facts,
        consensus_targets=consensus_targets,
        first_vote_target=first_vote_target,
        own_speech=own_speech,
        observation=observation,
        recent_death=recent_death,
    )


def build_summary_task(
    config: GameConfig,
    day: int,
    speeches: dict[str, str],
    alive: list[str],
) -> str:
    return render_template(
        config.prompts["summary_task"],
        day=day,
        speeches_json=json.dumps(speeches, ensure_ascii=False, indent=2),
    )
