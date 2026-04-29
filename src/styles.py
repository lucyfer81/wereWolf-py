from __future__ import annotations

from src.models import VoteStyleKey, DEFAULT_VOTING_STYLES

VOTING_STYLE_CARDS: dict[VoteStyleKey, dict] = {
    "conservative": {
        "name": "保守谨慎型",
        "rules": "无确凿证据时弃票（投给自己），不急于站队",
        "scenarios": [
            "场景1：Day 1 没有人提出实质性指控时，选择观望",
            "场景2：看到多人互相指控但逻辑都薄弱时，不急于站队",
        ],
    },
    "pressure": {
        "name": "施压型",
        "rules": "Day 1 倾向投票给理由最弱的发言者",
        "scenarios": [
            "场景1：某人的发言仅为「我觉得 XXX 可疑」而无具体行为时，优先投他",
            "场景2：多人保持观望时，主动制造压力迫使表态",
        ],
    },
    "contrarian": {
        "name": "反共识型",
        "rules": "当多人迅速聚焦同一目标时，优先评估「最早提出主叙事的人」而非直接投给被聚焦者",
        "scenarios": [
            "场景1：看到 3 人同投 Seat1 时，检查谁最先指控 Seat1，评估其是否在带节奏",
            "场景2：不直接投给被聚焦者，而是投给「造势者」",
        ],
    },
    "logic_driven": {
        "name": "逻辑驱动型",
        "rules": "优先抓自相矛盾或论据跳跃的发言",
        "scenarios": [
            "场景1：发现某人前后发言矛盾（例如先说观察 XXX 后又投 XXX），标记为可疑",
            "场景2：某人论据从行为 A 跳到行为 B 而无逻辑链条，重点怀疑",
        ],
    },
}


def get_style_for_player(player: str) -> VoteStyleKey:
    return DEFAULT_VOTING_STYLES.get(player, "conservative")
