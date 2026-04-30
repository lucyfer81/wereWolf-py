from __future__ import annotations

from src.config_loader import GameConfig


def get_style_for_player(player: str, config: GameConfig) -> str:
    seat_num = int(player.replace("Seat", ""))
    style_key = config.style_assignment.get(seat_num, "conservative")
    return style_key


def get_style_card(style_key: str, config: GameConfig) -> dict:
    return config.voting_styles[style_key]
