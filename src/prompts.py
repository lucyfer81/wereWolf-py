from __future__ import annotations

import json


def build_player_system_prompt(
    player_name: str,
    role: str,
    role_info: str,
    style_name: str,
    style_rules: str,
    style_scenarios: str,
    night_action: str,
) -> str:
    return f"""# 狼人杀游戏：你是一名玩家

## 当前处境

你现在身处一个有8名玩家的村庄，其中有2名隐藏的狼人。
- 你的座位号：**{player_name}**（你就是这个玩家）
- 你的身份：**{role}**
- 你知道的信息：{role_info}
- 其他玩家：Seat1 - Seat8

## 你的投票风格

你是 {style_name} 型玩家。

规则：{style_rules}

场景示例：
{style_scenarios}

## 你不知道的信息

除了身份卡透露的信息外，你不知道任何人的真实身份。
你只能通过他们的发言、投票、行为来判断谁是敌人。
你必须承认自己不知道，不能假装确定或编造不存在的信息。
你必须始终把"我"理解为 {player_name} 本人。
白天发言时禁止怀疑或指控自己；投票时允许因观望投给自己，但这不等同于自我指控。

## 夜晚发生什么

{night_action}

## 输出格式

请以 JSON 格式回复：
{{
  "action": "speech | vote | night_action",
  "target": "Seat1 | Seat2 | Seat3 | Seat4 | Seat5 | Seat6 | Seat7 | Seat8",
  "content": "你的发言内容或决策理由（<=120字）",
  "confidence": "high | medium | low",
  "risk_if_wrong": "如果投错会导致什么后果（投票时必须填写）",
  "alt_target": "备选目标（必须是不同于 target 的存活玩家）",
  "target_vs_alt_reason": "为什么 target 比 alt_target 更可疑（>=8字）",
  "evidence": ["证据1（含《可核查引用》）", "证据2（含《可核查引用》）"],
  "changed_vote": false,
  "why_change": ""
}}"""


def build_gm_system_prompt() -> str:
    return """# 狼人杀游戏管理员 (GameMaster)

你是狼人杀游戏的 Game Master（游戏管理员），负责推进游戏流程和裁决胜负。
你只需要输出 JSON，不要输出额外文本。"""


def build_night_task(
    day: int,
    teammates: list[str],
    alive_players: list[str],
    observation: str = "",
) -> str:
    parts = [
        f"现在是第 {day} 天夜晚。",
        "",
        f"你是狼人。你的同伴：{', '.join(teammates) or '（无）'}",
        f"当前存活玩家：{', '.join(alive_players)}",
        "请选择今晚的击杀目标。",
        "小提示：过于完美的推理可能引起注意，偶尔保持模糊更安全。",
    ]
    if observation:
        parts.append(f"你之前关注的观察对象：{observation}")
    return "\n".join(parts)


def build_speech_task(
    player: str,
    role: str,
    day: int,
    alive: list[str],
    prior_speeches: dict[str, str],
    observation: str,
    evidence_facts: str,
) -> str:
    parts = [
        f"现在是第 {day} 天白天。",
        f'你当前座位：{player}（你就是"我"）',
        f"你的身份：{role}",
        f"当前存活玩家：{', '.join(alive)}",
        "",
    ]

    if prior_speeches:
        parts.append("之前的发言记录：")
        parts.append(json.dumps(prior_speeches, ensure_ascii=False, indent=2))
        parts.append("")

    if observation:
        parts.append(f"你观察的重点是：{observation}")
        parts.append("")

    parts.append("可核查公共事实（evidence 必须引用其中原文片段）：")
    parts.append(evidence_facts)
    parts.append("")

    if day == 1:
        parts.append("请进行你的发言（<=120字）。你可以点名怀疑对象并给理由，或说明暂时观望。")
        parts.append(f"如果你点名怀疑对象，target 不能是你自己（{player}）。")
    else:
        parts.append("请进行你的发言（<=120字），必须包含怀疑对象和理由。")
        parts.append(f"必须在 target 字段填写你怀疑的存活玩家，且 target 不能是你自己（{player}）。")
    parts.append('禁止出现"我怀疑自己 / 我觉得自己像狼 / 我投自己因为我是狼"这类自我指控。')
    parts.append("你必须填写 evidence 数组，至少1条；每条都要包含《引用片段》且可在公共事实中找到。")

    if role == "werewolf":
        parts.append("小提示：过于完美的推理可能引起注意，偶尔保持模糊更安全。")

    return "\n".join(parts)


def build_first_vote_task(
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
    parts = [
        f"现在是第 {day} 天白天【第一轮：初投】。",
        f"你的身份：{role}",
        f"当前存活玩家：{', '.join(alive)}",
        "",
        "GM公共公告摘要：",
        day_summary,
        "",
        "可核查公共事实（evidence 必须引用其中原文片段）：",
        evidence_facts,
        "",
        f"你今天的发言：\"{own_speech}\"",
        "",
        "投票约束：",
        "- 这是第一轮私下投票，结果不会立即公开",
        "- 你必须在 risk_if_wrong 字段填写投错代价（>=6字）",
        "- 你必须填写 evidence 数组，至少2条；每条都要包含《引用片段》且可在公共事实中找到",
        "- 你必须填写 alt_target，且 alt_target 必须是不同于 target 的存活玩家",
        "- 你必须填写 target_vs_alt_reason（>=8字），说明为何 target 比 alt_target 更可疑",
        "- 不要盲目跟风，基于摘要和你自己的发言决策",
        "",
        "请投票给你认为最可能是狼人的玩家，或投给自己表示观望。",
    ]
    if recent_death:
        parts.append(f"最近一次死亡：{recent_death}")
    if observation:
        parts.append(f"记住你要观察的对象：{observation}")
    return "\n".join(parts)


def build_second_vote_task(
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
    parts = [
        f"现在是第 {day} 天白天【第二轮：终投】。",
        f"你的身份：{role}",
        f"当前存活玩家：{', '.join(alive)}",
        "",
        "GM公共公告摘要：",
        day_summary,
        "",
        vote_distribution,
        "",
        "可核查公共事实（evidence 必须引用其中原文片段）：",
        evidence_facts,
        "",
        f"当前最高票目标：{', '.join(consensus_targets) or '（无）'}",
        f"你第一轮投给了：{first_vote_target}",
        f"你今天的发言：\"{own_speech}\"",
        "",
        "投票约束：",
        "- 你可以看到第一轮票型分布，据此调整决策",
        "- 你必须填写 evidence 数组，至少2条；每条都要包含《引用片段》且可在公共事实中找到",
        "- 你必须填写 alt_target，且 alt_target 必须是不同于 target 的存活玩家",
        "- 你必须填写 target_vs_alt_reason（>=8字），说明为何 target 比 alt_target 更可疑",
        '- 若 target 命中当前最高票目标，必须额外给出至少一条指向该目标的独立证据（不能只说"大家都投"）',
        "- 改票时 changed_vote 必须为 true",
        "- 改票时 why_change 必须>=5字，否则改票无效",
        "- 不改票时 changed_vote=false，why_change 为空",
        "",
        "请进行你的终投。",
    ]
    if recent_death:
        parts.append(f"最近一次死亡：{recent_death}")
    if observation:
        parts.append(f"记住你要观察的对象：{observation}")
    return "\n".join(parts)


def build_summary_task(
    day: int,
    speeches: dict[str, str],
    alive: list[str],
) -> str:
    return "\n".join([
        f"请为第 {day} 天的发言生成投票摘要。",
        "以下是今天所有存活玩家的发言：",
        json.dumps(speeches, ensure_ascii=False, indent=2),
        "你必须只输出 JSON：{\"summary\":\"...\"}。",
        "summary 必须仅包含事实，不表达立场，且最多 6 行。",
        "每行尽量覆盖：点名怀疑对象、支持/反对对象、是否给出理由、是否质疑带节奏。",
    ])
