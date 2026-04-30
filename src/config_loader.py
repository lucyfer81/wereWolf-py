from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml
from jinja2 import BaseLoader, Environment


_env = Environment(loader=BaseLoader(), keep_trailing_newline=True)


@dataclass
class RoleConfig:
    key: str
    team: str
    count: int
    night_action: bool
    shared_memory: bool
    night_priority: int
    role_info_template: str
    night_action_template: str
    night_task_hint: str
    on_death_template: str | None = None


@dataclass
class GameConfig:
    total_players: int
    roles: dict[str, RoleConfig]
    voting_styles: dict[str, dict[str, Any]]
    style_assignment: dict[int, str]
    prompts: dict[str, str]
    settings: dict[str, Any]


def load_config(path: Path | str) -> GameConfig:
    path = Path(path)
    if not path.exists():
        raise FileNotFoundError(f"Config file not found: {path}")
    with open(path, "r", encoding="utf-8") as f:
        raw = yaml.safe_load(f)

    roles: dict[str, RoleConfig] = {}
    for key, r in raw["roles"].items():
        roles[key] = RoleConfig(
            key=key,
            team=r["team"],
            count=r["count"],
            night_action=r.get("night_action", False),
            shared_memory=r.get("shared_memory", False),
            night_priority=r.get("night_priority", 99),
            role_info_template=r.get("role_info_template", ""),
            night_action_template=r.get("night_action_template", ""),
            night_task_hint=r.get("night_task_hint", ""),
            on_death_template=r.get("on_death_template"),
        )

    style_assignment: dict[int, str] = {}
    for entry in raw.get("style_assignment", []):
        style_assignment[entry["seat"]] = entry["style"]

    return GameConfig(
        total_players=raw["game"]["total_players"],
        roles=roles,
        voting_styles=raw.get("voting_styles", {}),
        style_assignment=style_assignment,
        prompts=raw.get("prompts", {}),
        settings=raw.get("settings", {}),
    )


def render_template(template: str, **kwargs: Any) -> str:
    return _env.from_string(template).render(**kwargs)


def validate_config(config: GameConfig) -> list[str]:
    errors: list[str] = []
    role_total = sum(r.count for r in config.roles.values())
    if role_total != config.total_players:
        errors.append(f"角色人数之和({role_total}) != total_players({config.total_players})")
    teams = {r.team for r in config.roles.values()}
    if "werewolves" not in teams:
        errors.append("缺少狼人阵营角色")
    if "villagers" not in teams:
        errors.append("缺少村民阵营角色")
    return errors
