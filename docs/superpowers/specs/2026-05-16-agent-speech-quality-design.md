# Agent 发言质量改进设计

日期：2026-05-16

## 问题

AI 玩家发言跳脱、缺乏连贯性和个性差异。根因分析：

1. `prior_speeches` 缺少 target 信息，AI 不知道前面的人在指控谁
2. 发言阶段没有风格约束，所有玩家语气趋同
3. `memory_context` 裸拼接在 task 前，容易被模型忽略
4. `evidence_facts` 可能混入私有信息（防御性修复）
5. 每次调用创建新 Agent，玩家没有持续上下文

## 改进 1：prior_speeches 加入 target

**文件**：`src/prompts.py`、`src/game.py`、`src/models.py`

- `DayProgress` 新增 `speech_targets: dict[str, str]`，记录每个发言者的 target
- `_run_speeches` 中记录发言时同步写入 `PlayerResponse.target`
- `build_speech_task` 中格式化 prior_speeches_numbered 为：
  ```
  第1位 Seat3（指向 Seat5）：发言内容……
  ```
- Day1 无 target 时省略括号部分
- `speech_task` 模板中相应更新说明文字

## 改进 2：speech_task 注入发言风格

**文件**：`configs/default-8p.yaml`、`configs/classic-9p.yaml`、`src/prompts.py`

- 每种 `voting_styles` 新增 `speech_hints` 字段，描述发言行为特征：
  - conservative：观望分析，不主动点名，语气温和
  - pressure：主动出击，直接点名，语气强硬
  - contrarian：关注叙事者可信度，指出推理漏洞
  - logic_driven：注重逻辑链条，推理严谨有条理
- `build_speech_task` 中读取当前玩家的 `speech_hints`，注入到 speech_task 模板中
- 需要将 style_key 传入 `build_speech_task`，或直接传入 speech_hints 字符串

## 改进 3：memory_context 指令包装

**文件**：`src/game.py`（三处注入点：697-701、809-813、915-919）

- 将裸拼接 `memory_context + "\n\n" + task` 改为：
  ```python
  task = (
      "## 你的历史记忆（请保持发言与历史立场一致，不要自相矛盾）\n"
      f"{memory_context}\n\n"
      "## 当前任务\n"
      f"{task}"
  )
  ```
- 三处统一格式

## 改进 4：evidence_facts 信息泄露防御

**文件**：`src/game.py`

- 审计所有 `add_public_event` 调用点的 content/details 字段
- `_build_evidence_facts` 增加安全过滤：只取 `event.phase == "day"` 的事件
- 确认死亡公告 content 不含死因细节（如"被狼人杀害"应改为"昨晚死亡"）
- 确认 details 字段不会通过其他渠道传给玩家

## 改进 5：增强单轮 prompt 上下文延续

**文件**：`src/models.py`、`src/game.py`

### a) 立场摘要

- `PlayerMemory` 新增 `stance_log: dict[int, str]`（day -> stance）
- reflection 阶段将 `observation` 截取为简短立场声明，存入 stance_log
- `get_prompt_context` 中输出 stance_log

### b) 结构化记忆格式

- `get_day_context` 输出改为带 markdown 标记的结构化格式：
  ```
  ### Day1 我的发言
  > 发言内容……（指向Seat5）

  ### Day1 我的投票
  > 投票给Seat5

  ### Day2 存活变化
  > Seat3 死亡
  ```

### c) reflection 阶段同步更新

- `_run_reflection` 中，reflection 返回后提取 observation 的核心立场
- 截取为一句简短声明存入 `stance_log[current_day]`

## 不做的事

- 不改为多轮对话历史方式（保持单轮调用 + 增强上下文）
- 不重构 Agent 创建流程
- 不修改 voting_style 原有定义和投票行为逻辑
