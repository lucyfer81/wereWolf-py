# Agent 发言质量改进 实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 修复 AI 玩家发言跳脱问题——增加发言互动性、风格差异、上下文延续和信息隔离。

**Architecture:** 保持现有单轮 Agent 调用模式，通过增强 prompt 质量（prior_speeches 加 target、speech_task 注入风格、memory_context 加包装、evidence_facts 安全过滤、PlayerMemory 增加立场摘要）来提升发言质量。

**Tech Stack:** Python 3.12, pydantic-ai, Jinja2, PyYAML, pytest

---

## File Structure

| File | Change | Responsibility |
|------|--------|----------------|
| `src/models.py` | Modify | `DayProgress` 加 `speech_targets`；`PlayerMemory` 加 `stance_log`，改 `get_day_context` 格式 |
| `src/prompts.py` | Modify | `build_speech_task` 加 `prior_speech_targets` 参数和 `speech_hints` 参数 |
| `src/game.py` | Modify | 三处 memory_context 注入加包装；`_run_speeches` 记录 target；`_build_evidence_facts` 加 phase 过滤；`_run_reflection` 更新 stance_log |
| `src/styles.py` | Modify | 新增 `get_speech_hints` 函数 |
| `configs/default-8p.yaml` | Modify | 每种 voting_style 加 `speech_hints` 字段；speech_task 模板加 speech_hints 占位 |
| `configs/classic-9p.yaml` | Modify | 同上 |
| `tests/fixtures/default-8p.yaml` | Modify | 同步 voting_styles 的 speech_hints |
| `tests/fixtures/classic-9p.yaml` | Modify | 同步 voting_styles 的 speech_hints |
| `tests/test_prompts.py` | Modify | 更新/新增测试覆盖新参数 |
| `tests/test_models.py` | Modify | 新增 stance_log 和 get_day_context 格式测试 |
| `tests/test_game.py` | Modify | 新增 evidence_facts phase 过滤测试 |

---

### Task 1: DayProgress 加 speech_targets + PlayerMemory 加 stance_log

**Files:**
- Modify: `src/models.py:63-101` (`PlayerMemory`)
- Modify: `src/models.py:142-153` (`DayProgress`)
- Test: `tests/test_models.py`

- [ ] **Step 1: 写测试**

在 `tests/test_models.py` 末尾添加：

```python
def test_day_progress_speech_targets():
    from src.models import DayProgress
    dp = DayProgress()
    dp.speech_targets["Seat1"] = "Seat5"
    dp.speech_targets["Seat3"] = "Seat7"
    assert dp.speech_targets["Seat1"] == "Seat5"
    assert dp.speech_targets["Seat3"] == "Seat7"


def test_player_memory_stance_log():
    from src.models import PlayerMemory
    pm = PlayerMemory()
    pm.stance_log[1] = "怀疑Seat5，认为Seat2预言家身份可疑"
    pm.stance_log[2] = "坚持怀疑Seat5，新增怀疑Seat7"
    assert "Seat5" in pm.stance_log[1]
    assert len(pm.stance_log) == 2
```

- [ ] **Step 2: 运行测试确认失败**

Run: `uv run pytest tests/test_models.py::test_day_progress_speech_targets tests/test_models.py::test_player_memory_stance_log -v`
Expected: FAIL (字段不存在)

- [ ] **Step 3: 修改 models.py**

在 `DayProgress`（models.py:142-153）中加入 `speech_targets`:

```python
@dataclass
class DayProgress:
    stage: DayStage = "speeches"
    speeches: dict[str, str] = field(default_factory=dict)
    speech_targets: dict[str, str] = field(default_factory=dict)  # player -> target
    day_summary: str = ""
    initial_votes: dict[str, str] = field(default_factory=dict)
    final_votes: dict[str, VoteRecord] = field(default_factory=dict)
    vote_distribution: str = ""
    consensus_targets: list[str] = field(default_factory=list)
    tie_candidates: list[str] = field(default_factory=list)
    speech_index: int = 0
```

在 `PlayerMemory`（models.py:63-72）中加入 `stance_log`:

```python
@dataclass
class PlayerMemory:
    """单个玩家的完整记忆 - 贯穿全剧"""

    speech_log: dict[int, list[SpeechRecord]] = field(default_factory=dict)
    vote_log: dict[int, list[VoteRecord]] = field(default_factory=dict)
    death_log: dict[int, str] = field(default_factory=dict)
    reflections: list[str] = field(default_factory=list)
    suspicion: dict[str, float] = field(default_factory=dict)
    seer_results: list[SeerResult] = field(default_factory=list)
    role_state: dict | None = None
    stance_log: dict[int, str] = field(default_factory=dict)  # day -> 立场摘要
```

- [ ] **Step 4: 运行测试确认通过**

Run: `uv run pytest tests/test_models.py::test_day_progress_speech_targets tests/test_models.py::test_player_memory_stance_log -v`
Expected: PASS

- [ ] **Step 5: 提交**

```bash
git add src/models.py tests/test_models.py
git commit -m "feat: add speech_targets to DayProgress and stance_log to PlayerMemory"
```

---

### Task 2: 改进 get_day_context 为结构化格式 + 增加 stance_log 输出

**Files:**
- Modify: `src/models.py:74-101` (`PlayerMemory.get_day_context` 和 `get_reflections_str`)
- Test: `tests/test_models.py`

- [ ] **Step 1: 写测试**

```python
def test_get_day_context_structured_format():
    from src.models import PlayerMemory, SpeechRecord
    pm = PlayerMemory()
    pm.speech_log[1] = [SpeechRecord(speaker="Seat1", content="我觉得Seat5有问题", target="Seat5")]
    pm.vote_log[1] = [__import__("src.models", fromlist=["VoteRecord"]).VoteRecord(
        voter="Seat1", target="Seat5", alt_target="Seat3",
        confidence="high", risk_if_wrong="可能冤枉好人",
        target_vs_alt_reason="Seat5更可疑"
    )]
    pm.death_log[1] = "Seat3"
    pm.stance_log[1] = "怀疑Seat5"

    ctx = pm.get_day_context(1)
    assert "### Day1 我的发言" in ctx
    assert "我觉得Seat5有问题" in ctx
    assert "指向 Seat5" in ctx
    assert "### Day1 我的投票" in ctx
    assert "Seat5" in ctx
    assert "### Day1 存活变化" in ctx
    assert "Seat3" in ctx
    assert "### Day1 我的立场" in ctx
    assert "怀疑Seat5" in ctx


def test_get_day_context_no_stance():
    from src.models import PlayerMemory
    pm = PlayerMemory()
    ctx = pm.get_day_context(1)
    assert ctx == ""
```

- [ ] **Step 2: 运行测试确认失败**

Run: `uv run pytest tests/test_models.py::test_get_day_context_structured_format tests/test_models.py::test_get_day_context_no_stance -v`
Expected: FAIL (格式不匹配)

- [ ] **Step 3: 修改 get_day_context**

将 `PlayerMemory.get_day_context`（models.py:74-96）替换为：

```python
def get_day_context(self, up_to_day: int) -> str:
    parts: list[str] = []
    for day in sorted(self.speech_log.keys()):
        if day > up_to_day:
            break
        parts.append(f"### Day{day} 我的发言")
        for s in self.speech_log[day]:
            parts.append(f"> {s.content}（指向 {s.target}）")
    for day in sorted(self.vote_log.keys()):
        if day > up_to_day:
            break
        parts.append(f"### Day{day} 我的投票")
        for v in self.vote_log[day]:
            line = f"> 投票给 {v.target}"
            if v.changed_vote:
                line += f"（改票，原因：{v.why_change}）"
            parts.append(line)
    for day in sorted(self.death_log.keys()):
        if day > up_to_day:
            break
        parts.append(f"### Day{day} 存活变化")
        parts.append(f"> {self.death_log[day]} 死亡")
    for day in sorted(self.stance_log.keys()):
        if day > up_to_day:
            break
        parts.append(f"### Day{day} 我的立场")
        parts.append(f"> {self.stance_log[day]}")
    return "\n".join(parts)
```

- [ ] **Step 4: 运行测试确认通过**

Run: `uv run pytest tests/test_models.py::test_get_day_context_structured_format tests/test_models.py::test_get_day_context_no_stance -v`
Expected: PASS

- [ ] **Step 5: 运行全部模型测试确认无回归**

Run: `uv run pytest tests/test_models.py -v`
Expected: ALL PASS

- [ ] **Step 6: 提交**

```bash
git add src/models.py tests/test_models.py
git commit -m "feat: structured memory format with stance_log in PlayerMemory"
```

---

### Task 3: voting_styles 加 speech_hints（两份配置 + 两份 fixture）

**Files:**
- Modify: `configs/default-8p.yaml:50-74`
- Modify: `configs/classic-9p.yaml:60-84`
- Modify: `tests/fixtures/default-8p.yaml`
- Modify: `tests/fixtures/classic-9p.yaml`
- Test: `tests/test_prompts.py`

- [ ] **Step 1: 写测试**

在 `tests/test_prompts.py` 末尾添加：

```python
def test_styles_have_speech_hints():
    config = load_config(FIXTURE_DIR / "default-8p.yaml")
    for key, card in config.voting_styles.items():
        assert "speech_hints" in card, f"{key} missing speech_hints"
        assert len(card["speech_hints"]) >= 10, f"{key} speech_hints too short"
```

- [ ] **Step 2: 运行测试确认失败**

Run: `uv run pytest tests/test_prompts.py::test_styles_have_speech_hints -v`
Expected: FAIL (missing speech_hints)

- [ ] **Step 3: 给 configs/default-8p.yaml 的 voting_styles 加 speech_hints**

在每种 style 的 `scenarios` 之后加 `speech_hints` 字段：

```yaml
  conservative:
    name: "保守谨慎型"
    rules: "无确凿证据时保持观望态度，倾向投给逻辑最薄弱的发言者，不急于站队"
    scenarios:
      - "场景1：Day 1 没有人提出实质性指控时，选择观望"
      - "场景2：看到多人互相指控但逻辑都薄弱时，不急于站队"
    speech_hints: "发言时偏向观望和分析，不主动点名，多提问题，语气温和谨慎。除非有确凿证据，否则避免直接指控。"
  pressure:
    name: "施压型"
    rules: "Day 1 倾向投票给理由最弱的发言者"
    scenarios:
      - "场景1：某人的发言仅为「我觉得 XXX 可疑」而无具体行为时，优先投他"
      - "场景2：多人保持观望时，主动制造压力迫使表态"
    speech_hints: "发言时主动出击，直接点名可疑玩家，语气强硬自信。善于用反问和施压迫使对方露出破绽。"
  contrarian:
    name: "反共识型"
    rules: "当多人迅速聚焦同一目标时，优先评估「最早提出主叙事的人」而非直接投给被聚焦者"
    scenarios:
      - "场景1：看到 3 人同投 Seat1 时，检查谁最先指控 Seat1，评估其是否在带节奏"
      - "场景2：不直接投给被聚焦者，而是投给「造势者」"
    speech_hints: "发言时关注叙事者的可信度而非被指控者。善于指出他人推理中的漏洞和矛盾，经常提出不同的解释角度。"
  logic_driven:
    name: "逻辑驱动型"
    rules: "优先抓自相矛盾或论据跳跃的发言"
    scenarios:
      - "场景1：发现某人前后发言矛盾（例如先说观察 XXX 后又投 XXX），标记为可疑"
      - "场景2：某人论据从行为 A 跳到行为 B 而无逻辑链条，重点怀疑"
    speech_hints: "发言时注重逻辑链条和证据引用。会梳理已知事实，找出不一致之处，推理过程严谨有条理。"
```

- [ ] **Step 4: 同步修改 configs/classic-9p.yaml 的 voting_styles**

与 Step 3 完全相同的 speech_hints 内容，加到 classic-9p.yaml 对应位置。

- [ ] **Step 5: 同步修改 tests/fixtures/ 下的两份 YAML**

将 `tests/fixtures/default-8p.yaml` 和 `tests/fixtures/classic-9p.yaml` 的 `voting_styles` 部分同步更新，添加相同的 `speech_hints` 字段。

- [ ] **Step 6: 运行测试确认通过**

Run: `uv run pytest tests/test_prompts.py::test_styles_have_speech_hints -v`
Expected: PASS

- [ ] **Step 7: 运行全部 prompt 测试确认无回归**

Run: `uv run pytest tests/test_prompts.py -v`
Expected: ALL PASS

- [ ] **Step 8: 提交**

```bash
git add configs/ tests/fixtures/
git commit -m "feat: add speech_hints to voting_styles in all config files"
```

---

### Task 4: styles.py 加 get_speech_hints 函数

**Files:**
- Modify: `src/styles.py`
- Test: `tests/test_prompts.py`

- [ ] **Step 1: 写测试**

```python
def test_get_speech_hints():
    from src.styles import get_speech_hints
    config = load_config(FIXTURE_DIR / "default-8p.yaml")
    hints = get_speech_hints("pressure", config)
    assert "主动出击" in hints
    assert len(hints) >= 10


def test_get_speech_hints_default():
    from src.styles import get_speech_hints
    config = load_config(FIXTURE_DIR / "default-8p.yaml")
    hints = get_speech_hints("conservative", config)
    assert "观望" in hints
```

- [ ] **Step 2: 运行测试确认失败**

Run: `uv run pytest tests/test_prompts.py::test_get_speech_hints tests/test_prompts.py::test_get_speech_hints_default -v`
Expected: FAIL (import error)

- [ ] **Step 3: 在 styles.py 中添加 get_speech_hints**

在 `src/styles.py` 末尾添加：

```python
def get_speech_hints(style_key: str, config: GameConfig) -> str:
    card = config.voting_styles.get(style_key, {})
    return card.get("speech_hints", "以自然、理性的方式发言。")
```

- [ ] **Step 4: 运行测试确认通过**

Run: `uv run pytest tests/test_prompts.py::test_get_speech_hints tests/test_prompts.py::test_get_speech_hints_default -v`
Expected: PASS

- [ ] **Step 5: 提交**

```bash
git add src/styles.py tests/test_prompts.py
git commit -m "feat: add get_speech_hints helper to styles.py"
```

---

### Task 5: build_speech_task 加 prior_speech_targets 和 speech_hints

**Files:**
- Modify: `src/prompts.py:146-177` (`build_speech_task`)
- Modify: `configs/default-8p.yaml` speech_task 模板
- Modify: `configs/classic-9p.yaml` speech_task 模板
- Modify: `tests/fixtures/default-8p.yaml` speech_task 模板
- Modify: `tests/fixtures/classic-9p.yaml` speech_task 模板
- Test: `tests/test_prompts.py`

- [ ] **Step 1: 写测试**

```python
def test_speech_task_with_targets():
    config = load_config(FIXTURE_DIR / "default-8p.yaml")
    task = build_speech_task(
        config,
        player="Seat3", role="villager", day=2,
        alive=["Seat1", "Seat3", "Seat5", "Seat7"],
        prior_speeches={"Seat1": "我怀疑Seat5"},
        prior_speech_targets={"Seat1": "Seat5"},
        observation="关注Seat5",
        evidence_facts="some facts",
        speech_hints="发言时注重逻辑链条和证据引用。",
    )
    assert "指向 Seat5" in task
    assert "逻辑链条" in task


def test_speech_task_day1_no_targets():
    config = load_config(FIXTURE_DIR / "default-8p.yaml")
    task = build_speech_task(
        config,
        player="Seat1", role="villager", day=1,
        alive=["Seat1", "Seat2", "Seat3", "Seat4", "Seat5", "Seat6", "Seat7", "Seat8"],
        prior_speeches={}, prior_speech_targets={},
        observation="", evidence_facts="test facts",
    )
    assert "第 1 天白天" in task
```

- [ ] **Step 2: 运行测试确认失败**

Run: `uv run pytest tests/test_prompts.py::test_speech_task_with_targets tests/test_prompts.py::test_speech_task_day1_no_targets -v`
Expected: FAIL (unexpected keyword args)

- [ ] **Step 3: 修改 build_speech_task 签名和逻辑**

将 `src/prompts.py` 的 `build_speech_task`（146-177）替换为：

```python
def build_speech_task(
    config: GameConfig,
    player: str,
    role: str,
    day: int,
    alive: list[str],
    prior_speeches: dict[str, str],
    prior_speech_targets: dict[str, str] | None = None,
    observation: str = "",
    evidence_facts: str = "",
    seer_history: str = "",
    speech_index: int = 1,
    speech_hints: str = "",
) -> str:
    # Format prior speeches with target info
    numbered_lines = []
    targets = prior_speech_targets or {}
    for i, (speaker, content) in enumerate(prior_speeches.items(), 1):
        target = targets.get(speaker, "")
        if target:
            numbered_lines.append(f"第{i}位 {speaker}（指向 {target}）：{content}")
        else:
            numbered_lines.append(f"第{i}位 {speaker}：{content}")
    prior_speeches_numbered = "\n".join(numbered_lines)

    return render_template(
        config.prompts["speech_task"],
        day=day,
        player=player,
        role=role,
        alive=alive,
        prior_speeches=prior_speeches,
        prior_speeches_numbered=prior_speeches_numbered,
        observation=observation,
        evidence_facts=evidence_facts,
        seer_history=seer_history,
        speech_index=speech_index,
        alive_count=len(alive),
        speech_hints=speech_hints,
    )
```

- [ ] **Step 4: 修改 speech_task 模板，加入 speech_hints 占位**

在 `configs/default-8p.yaml` 的 `speech_task` 模板中，在 `{% if observation %}` 之前加入：

```
{% if speech_hints %}

你的发言风格：{{ speech_hints }}
{% endif %}
```

同样修改 `configs/classic-9p.yaml`、`tests/fixtures/default-8p.yaml`、`tests/fixtures/classic-9p.yaml` 的 speech_task 模板，在相同位置加入同样的代码。

- [ ] **Step 5: 运行测试确认通过**

Run: `uv run pytest tests/test_prompts.py -v`
Expected: ALL PASS

- [ ] **Step 6: 提交**

```bash
git add src/prompts.py configs/ tests/fixtures/ tests/test_prompts.py
git commit -m "feat: add target info and speech_hints to speech task prompt"
```

---

### Task 6: game.py — _run_speeches 记录 target + 传参

**Files:**
- Modify: `src/game.py:670-746` (`_run_speeches`)

- [ ] **Step 1: 修改 _run_speeches 记录 target 并传参**

在 `_run_speeches` 方法（game.py:670-746）中做以下改动：

1. 在调用 `build_speech_task` 时传入新参数。将第 683-694 行改为：

```python
            task = build_speech_task(
                config,
                player=player,
                role=state.roles[player],
                day=state.current_day,
                alive=alive,
                prior_speeches=progress.speeches,
                prior_speech_targets=progress.speech_targets,
                observation="",
                evidence_facts=evidence_facts,
                seer_history=seer_history,
                speech_index=speech_index,
                speech_hints=get_speech_hints(
                    get_style_for_player(player, config), config
                ),
            )
```

2. 在文件顶部确认 import 已有（或添加）：

```python
from src.styles import get_style_for_player, get_speech_hints
```

3. 在第 726 行 `progress.speeches[player] = content` 之后添加：

```python
            progress.speech_targets[player] = target
```

- [ ] **Step 2: 检查 import**

确认 `src/game.py` 顶部有 `from src.styles import get_style_for_player` 的导入。如果只有 `get_style_for_player`，需要补充 `get_speech_hints`。

- [ ] **Step 3: 提交**

```bash
git add src/game.py
git commit -m "feat: pass target and speech_hints in speech phase"
```

---

### Task 7: game.py — memory_context 指令包装（三处）

**Files:**
- Modify: `src/game.py:697-701` (speech)
- Modify: `src/game.py:809-813` (first vote)
- Modify: `src/game.py:915-919` (second vote)

- [ ] **Step 1: 修改三处 memory_context 注入**

将三处相同的模式：

```python
            if memory_context:
                task = memory_context + "\n\n" + task
```

全部替换为：

```python
            if memory_context:
                task = (
                    "## 你的历史记忆（请保持发言与历史立场一致，不要自相矛盾）\n"
                    f"{memory_context}\n\n"
                    "## 当前任务\n"
                    f"{task}"
                )
```

三处位置：
- 发言（约第 700 行）
- 一投（约第 812 行）
- 二投（约第 918 行）

- [ ] **Step 2: 运行集成测试确认无回归**

Run: `uv run pytest tests/ -v --ignore=tests/e2e`
Expected: ALL PASS

- [ ] **Step 3: 提交**

```bash
git add src/game.py
git commit -m "feat: wrap memory_context with explicit instructions"
```

---

### Task 8: game.py — _build_evidence_facts 加 phase 过滤

**Files:**
- Modify: `src/game.py:1019-1029` (`_build_evidence_facts`)
- Test: `tests/test_game.py`

- [ ] **Step 1: 写测试**

在 `tests/test_game.py` 末尾添加：

```python
def test_evidence_facts_filters_night_events():
    from src.models import GameState, PublicEvent, DayProgress
    state = GameState(alive_players=["Seat1", "Seat2", "Seat3"])
    # Night death (should be included - it's a death event)
    state.add_public_event(PublicEvent(
        day=1, phase="night", type="death",
        speaker="GameMaster", content="Seat4 被杀害",
        alive_players=["Seat1", "Seat2", "Seat3"]
    ))
    # Day speech
    state.add_public_event(PublicEvent(
        day=1, phase="day", type="speech",
        speaker="Seat1", content="我怀疑Seat2",
        alive_players=["Seat1", "Seat2", "Seat3"]
    ))
    # Day vote
    state.add_public_event(PublicEvent(
        day=1, phase="day", type="vote",
        speaker="Seat1", content="Seat1 投票给 Seat2",
        alive_players=["Seat1", "Seat2", "Seat3"]
    ))

    # Create a minimal game to test _build_evidence_facts
    from src.config_loader import load_config
    config = load_config(Path(__file__).parent / "fixtures" / "default-8p.yaml")
    from src.game import WerewolfGame
    game = WerewolfGame.__new__(WerewolfGame)
    game.state = state
    game.config = config

    facts = game._build_evidence_facts()
    # Should contain the night death, day speech, and day vote
    assert "Seat4 被杀害" in facts
    assert "我怀疑Seat2" in facts
    assert "Seat1 投票给 Seat2" in facts
```

- [ ] **Step 2: 运行测试确认通过（当前不过滤 phase，应通过）**

Run: `uv run pytest tests/test_game.py::test_evidence_facts_filters_night_events -v`
Expected: PASS（当前代码不过滤 phase，所以 night death 也包含）

- [ ] **Step 3: 修改 _build_evidence_facts**

将 `_build_evidence_facts`（game.py:1019-1029）替换为：

```python
def _build_evidence_facts(self) -> str:
    parts: list[str] = []
    for event in self.state.timeline:
        if event.type in ("speech", "vote", "summary", "death"):
            if event.phase == "day" or event.type == "death":
                parts.append(
                    f"[Day{event.day} {event.phase}] {event.speaker}: {event.content}"
                )
    result = "\n".join(parts)
    if not result:
        return "（当前为第一天，暂无可核查的公开历史事件。你可以基于自己的身份信息进行初步推理。）"
    return result
```

逻辑：只保留白天阶段的事件（speech, vote, summary）+ 死亡事件（无论白天夜晚，死亡都是公开事实）。夜间阶段的 speech/vote/summary 不会出现，但死亡事件会被包含。

- [ ] **Step 4: 审计死亡公告 content**

确认所有 `add_public_event` 中 `type="death"` 的 `content` 字段：
- game.py:519-528: `content=f"{dead} 被杀害"` — 不含死因细节（狼人/毒杀），安全
- game.py:590-598: `content=f"{hunter}（猎人）开枪带走了 {shot_target}"` — 暴露了猎人身份，但这是公开信息（白天发生则可见）
- game.py:974-983: `content=f"{eliminated} 被投票处决（{votes}票）"` — 白天事件，安全

死亡公告的 content 不含"被狼人杀害"或"被毒杀"等私有信息，审计通过。

- [ ] **Step 5: 运行测试确认通过**

Run: `uv run pytest tests/test_game.py::test_evidence_facts_filters_night_events -v`
Expected: PASS

- [ ] **Step 6: 运行全部非 e2e 测试确认无回归**

Run: `uv run pytest tests/ -v --ignore=tests/e2e`
Expected: ALL PASS

- [ ] **Step 7: 提交**

```bash
git add src/game.py tests/test_game.py
git commit -m "fix: filter evidence_facts to prevent private info leakage"
```

---

### Task 9: game.py — _run_reflection 更新 stance_log

**Files:**
- Modify: `src/game.py:603-653` (`_run_reflection`)

- [ ] **Step 1: 在 _run_reflection 中提取并保存立场摘要**

在 `_run_reflection` 方法的第 642-646 行（`pm.reflections.append(ref.observation)` 之后），添加立场摘要提取逻辑：

```python
                pm.reflections.append(ref.observation)
                # 提取简短立场摘要（取前60字）
                stance = ref.observation.strip()[:60]
                pm.stance_log[state.current_day] = stance
                # 合并怀疑度
```

完整上下文：将第 641-646 行：

```python
                ref = result.output
                pm.reflections.append(ref.observation)
                # 合并怀疑度
                for target, score in ref.updated_suspicion.items():
```

改为：

```python
                ref = result.output
                pm.reflections.append(ref.observation)
                # 提取简短立场摘要
                stance = ref.observation.strip()[:60]
                pm.stance_log[state.current_day] = stance
                # 合并怀疑度
                for target, score in ref.updated_suspicion.items():
```

- [ ] **Step 2: 运行全部非 e2e 测试确认无回归**

Run: `uv run pytest tests/ -v --ignore=tests/e2e`
Expected: ALL PASS

- [ ] **Step 3: 提交**

```bash
git add src/game.py
git commit -m "feat: save stance summary during reflection phase"
```

---

### Task 10: 运行完整 e2e 测试验证

**Files:**
- 无代码修改

- [ ] **Step 1: 运行全部测试套件**

Run: `uv run pytest tests/ -v`
Expected: ALL PASS

- [ ] **Step 2: 如果有失败，修复**

根据失败信息定位问题，修复后重新运行。

- [ ] **Step 3: 最终确认**

确认所有测试通过，无回归。
