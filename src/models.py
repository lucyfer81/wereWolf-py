from __future__ import annotations

import uuid
import random
from dataclasses import dataclass, field
from typing import Literal


type Role = str  # 从 config 动态决定
type Winner = Literal["werewolves", "villagers", "none"]
type Phase = Literal["day", "night"]
type VoteStyleKey = str  # 从 config 动态决定
type DayStage = Literal["speeches", "summary", "first_vote", "second_vote", "resolve"]


@dataclass
class SpeechRecord:
    speaker: str
    content: str
    target: str
    evidence: list[str] = field(default_factory=list)
    confidence: str = "medium"


@dataclass
class VoteRecord:
    voter: str
    target: str
    alt_target: str
    confidence: str
    risk_if_wrong: str
    target_vs_alt_reason: str
    evidence: list[str] = field(default_factory=list)
    changed_vote: bool = False
    why_change: str = ""


@dataclass
class WitchState:
    antidote_used: bool = False
    poison_used: bool = False


@dataclass
class SeerResult:
    day: int
    target: str
    result: str  # "good" | "werewolf"


@dataclass
class PublicEvent:
    day: int
    phase: Phase
    type: str  # "death" | "speech" | "vote" | "summary" | "night_action" | "announcement"
    speaker: str
    content: str
    alive_players: list[str] = field(default_factory=list)
    details: dict | None = None


@dataclass
class PlayerMemory:
    """单个玩家的完整记忆 - 贯穿全剧"""

    speech_log: dict[int, list[SpeechRecord]] = field(default_factory=dict)
    vote_log: dict[int, list[VoteRecord]] = field(default_factory=dict)
    death_log: dict[int, str] = field(default_factory=dict)  # day -> 死亡玩家
    reflections: list[str] = field(default_factory=list)  # 按追加顺序，全量保留
    suspicion: dict[str, float] = field(default_factory=dict)  # player -> 怀疑分
    seer_results: list[SeerResult] = field(default_factory=list)
    role_state: dict | None = None  # per-role state like WitchState

    def get_day_context(self, up_to_day: int) -> str:
        parts: list[str] = []
        for day in sorted(self.speech_log.keys()):
            if day > up_to_day:
                break
            parts.append(f"=== 第{day}天发言 ===")
            for s in self.speech_log[day]:
                parts.append(f"  {s.speaker}: {s.content} (怀疑{s.target})")
        for day in sorted(self.vote_log.keys()):
            if day > up_to_day:
                break
            parts.append(f"=== 第{day}天投票 ===")
            for v in self.vote_log[day]:
                parts.append(
                    f"  {v.voter} -> {v.target}"
                    + (f" (改票，原因：{v.why_change})" if v.changed_vote else "")
                )
        for day in sorted(self.death_log.keys()):
            if day > up_to_day:
                break
            parts.append(f"=== 第{day}天死亡 ===")
            parts.append(f"  {self.death_log[day]} 被淘汰")
        return "\n".join(parts)

    def get_reflections_str(self) -> str:
        if not self.reflections:
            return ""
        return "=== 你的观察反思 ===\n" + "\n".join(self.reflections)


@dataclass
class WerewolfSharedMemory:
    """狼人共享记忆 - 仅狼人可见"""

    kills: dict[int, str] = field(default_factory=dict)  # day -> 击杀目标
    teammates: list[str] = field(default_factory=list)

    def to_str(self, up_to_day: int) -> str:
        parts = ["=== 狼人私有信息 ==="]
        parts.append(f"你的同伴：{', '.join(self.teammates)}")
        for day in sorted(self.kills.keys()):
            if day > up_to_day:
                break
            parts.append(f"第{day}晚击杀目标：{self.kills[day]}")
        return "\n".join(parts)


@dataclass
class GameMemory:
    """游戏总记忆管理器"""

    player_memories: dict[str, PlayerMemory] = field(default_factory=dict)
    werewolf_memory: WerewolfSharedMemory = field(default_factory=WerewolfSharedMemory)

    def get_prompt_context(self, player: str, role: str, role_teams: dict[str, str], day: int) -> str:
        mem = self.player_memories.get(player, PlayerMemory())
        parts: list[str] = []
        public = mem.get_day_context(day)
        if public:
            parts.append(public)
        reflections = mem.get_reflections_str()
        if reflections:
            parts.append(reflections)
        if role_teams.get(role) == "werewolves":
            parts.append(self.werewolf_memory.to_str(day))
        return "\n\n".join(parts)


@dataclass
class DayProgress:
    stage: DayStage = "speeches"
    speeches: dict[str, str] = field(default_factory=dict)  # player -> content
    day_summary: str = ""
    initial_votes: dict[str, str] = field(default_factory=dict)  # player -> target
    final_votes: dict[str, VoteRecord] = field(default_factory=dict)
    vote_distribution: str = ""
    consensus_targets: list[str] = field(default_factory=list)
    tie_candidates: list[str] = field(default_factory=list)  # 平票候选人（第二轮专用）
    speech_index: int = 0  # 当前发言到第几个玩家


@dataclass
class GameState:
    roles: dict[str, Role] = field(default_factory=dict)
    role_teams: dict[str, str] = field(default_factory=dict)  # role_key -> team
    alive_players: list[str] = field(default_factory=list)
    current_day: int = 1
    phase: Phase = "night"
    winner: Winner = "none"
    timeline: list[PublicEvent] = field(default_factory=list)
    game_log: list[PublicEvent] = field(default_factory=list)
    day_progress: DayProgress = field(default_factory=DayProgress)
    voting_styles: dict[str, VoteStyleKey] = field(default_factory=dict)
    memory: GameMemory = field(default_factory=GameMemory)
    game_id: str = ""

    def add_public_event(self, event: PublicEvent):
        self.timeline.append(event)
        self.game_log.append(event)

    def check_win(self) -> Winner:
        alive_wolves = sum(
            1 for p in self.alive_players
            if self.role_teams.get(self.roles[p]) == "werewolves"
        )
        alive_villagers = len(self.alive_players) - alive_wolves
        if alive_wolves == 0:
            return "villagers"
        if alive_wolves >= alive_villagers:
            return "werewolves"
        return "none"

    def sort_alive(self) -> list[str]:
        return sorted(self.alive_players, key=lambda s: int(s.replace("Seat", "")))


def create_new_game_state(config) -> GameState:
    from src.config_loader import GameConfig  # avoid circular

    total = config.total_players
    players = [f"Seat{i + 1}" for i in range(total)]

    # Build role pool: list of (role_key, team) pairs
    role_pool: list[tuple[str, str]] = []
    for role_key, role_cfg in config.roles.items():
        for _ in range(role_cfg.count):
            role_pool.append((role_key, role_cfg.team))

    random.shuffle(role_pool)

    roles: dict[str, Role] = {}
    role_teams: dict[str, str] = {}
    for i, player in enumerate(players):
        role_key, team = role_pool[i]
        roles[player] = role_key
        role_teams[role_key] = team

    # Shared memory roles
    shared_memory_roles = {k for k, v in config.roles.items() if v.shared_memory}
    wolf_names = sorted([p for p in players if roles[p] in shared_memory_roles])

    player_memories: dict[str, PlayerMemory] = {p: PlayerMemory() for p in players}
    werewolf_memory = WerewolfSharedMemory(teammates=wolf_names)

    game_memory = GameMemory(
        player_memories=player_memories,
        werewolf_memory=werewolf_memory,
    )

    style_map = {f"Seat{seat}": style for seat, style in config.style_assignment.items()}

    return GameState(
        roles=roles,
        role_teams=role_teams,
        alive_players=sorted(players, key=lambda s: int(s.replace("Seat", ""))),
        current_day=1,
        phase="night",
        winner="none",
        voting_styles=style_map,
        memory=game_memory,
        game_id=uuid.uuid4().hex[:8],
    )
