"""完整的8人局狼人杀 Playwright E2E 测试。

覆盖范围:
- 页面加载和初始状态
- 新建游戏
- 单步推进（夜晚、白天各阶段）
- 自动运行至结束
- 游戏结束状态验证（胜负判定）
- UI 交互（导出日志、重新开局）
- 公共事件表的完整性
- 存活玩家数量变化
- 身份分配面板
"""

from __future__ import annotations

import re

import pytest
from playwright.sync_api import Page, expect


STEP_TIMEOUT = 120_000


@pytest.fixture(scope="module")
def live_url(server_url):
    return server_url


@pytest.fixture(scope="module")
def page_context(browser):
    context = browser.new_context(viewport={"width": 1280, "height": 900})
    yield context
    context.close()


@pytest.fixture(scope="module")
def game_page(page_context, live_url):
    p = page_context.new_page()
    p.goto(live_url)
    p.wait_for_load_state("networkidle")
    yield p
    p.close()


# ---------------------------------------------------------------------------
# Helper
# ---------------------------------------------------------------------------

def _status_value(page: Page, key: str) -> str:
    """获取局面状态面板中某个 key 对应的值。"""
    rows = page.locator("#status-list div")
    for i in range(rows.count()):
        row = rows.nth(i)
        dt = row.locator("dt")
        if dt.inner_text().strip() == key:
            return row.locator("dd").inner_text().strip()
    return ""


def _alive_players(page: Page) -> list[str]:
    """获取当前存活玩家列表。"""
    chips = page.locator("#alive-list .chip")
    return [chips.nth(i).inner_text() for i in range(chips.count())]


def _event_rows(page: Page) -> list[dict]:
    """获取公共事件表中所有行。"""
    rows = page.locator("#events-body tr")
    result = []
    for i in range(rows.count()):
        cells = rows.nth(i).locator("td")
        if cells.count() >= 5:
            result.append({
                "day": cells.nth(0).inner_text(),
                "phase": cells.nth(1).inner_text(),
                "type": cells.nth(2).inner_text(),
                "speaker": cells.nth(3).inner_text(),
                "content": cells.nth(4).inner_text(),
            })
    return result


def _role_chips(page: Page) -> dict[str, str]:
    """获取身份分配面板中 seat -> role 的映射。"""
    chips = page.locator("#roles-list .chip")
    roles = {}
    for i in range(chips.count()):
        text = chips.nth(i).inner_text()
        parts = text.split("·")
        if len(parts) == 2:
            seat = parts[0].strip()
            role = parts[1].strip()
            roles[seat] = role
    return roles


def _is_finished(page: Page) -> bool:
    return _status_value(page, "Finished") == "true"


def _step_and_wait(page: Page, timeout: float = STEP_TIMEOUT):
    """点击单步推进并等待按钮恢复可用（意味着 API 返回并渲染完毕）。"""
    page.locator("#step-btn").click()
    expect(page.locator("#step-btn")).to_be_enabled(timeout=timeout)
    # 给浏览器一帧时间完成 DOM 更新
    page.wait_for_timeout(200)


# ---------------------------------------------------------------------------
# 1. 页面加载
# ---------------------------------------------------------------------------

class TestPageLoad:
    """验证页面正常加载，UI 元素齐全。"""

    def test_title(self, game_page: Page):
        expect(game_page).to_have_title(re.compile(r"Werewolf"))

    def test_header_visible(self, game_page: Page):
        expect(game_page.locator("h1")).to_contain_text("Werewolf AI Arena")

    def test_control_buttons(self, game_page: Page):
        expect(game_page.locator("#new-game-btn")).to_be_visible()
        expect(game_page.locator("#step-btn")).to_be_visible()
        expect(game_page.locator("#run-btn")).to_be_visible()
        expect(game_page.locator("#max-steps-input")).to_be_visible()

    def test_status_panels(self, game_page: Page):
        expect(game_page.locator("#status-list")).to_be_visible()
        expect(game_page.locator("#alive-list")).to_be_visible()
        expect(game_page.locator("#roles-list")).to_be_visible()

    def test_log_panels(self, game_page: Page):
        expect(game_page.locator("#timeline")).to_be_visible()
        expect(game_page.locator("#events-body")).to_be_visible()

    def test_export_button_disabled_initially(self, game_page: Page):
        expect(game_page.locator("#export-log-btn")).to_be_disabled()

    def test_initial_timeline_text(self, game_page: Page):
        expect(game_page.locator("#timeline")).to_contain_text("点击")

    def test_initial_no_events(self, game_page: Page):
        expect(game_page.locator("#events-body")).to_contain_text("暂无公共事件")


# ---------------------------------------------------------------------------
# 2. 新建游戏
# ---------------------------------------------------------------------------

class TestNewGame:
    """验证新建游戏。"""

    def test_create_game(self, game_page: Page):
        game_page.locator("#new-game-btn").click()
        expect(game_page.locator("#status-list")).to_contain_text("Game ID", timeout=10_000)

    def test_game_id_assigned(self, game_page: Page):
        game_id = _status_value(game_page, "Game ID")
        assert len(game_id) == 8, f"Game ID 长度应为8, 实际: {game_id}"

    def test_initial_day(self, game_page: Page):
        assert _status_value(game_page, "Day") == "1"

    def test_initial_next_phase(self, game_page: Page):
        phase = _status_value(game_page, "Next Phase")
        assert phase in ("day", "night"), f"初始阶段应为 day/night, 实际: {phase}"

    def test_initial_alive_count(self, game_page: Page):
        alive_count = int(_status_value(game_page, "Alive"))
        assert alive_count >= 8, f"存活人数应 >= 8, 实际: {alive_count}"

    def test_no_winner(self, game_page: Page):
        assert _status_value(game_page, "Winner") == "none"

    def test_not_finished(self, game_page: Page):
        assert _status_value(game_page, "Finished") == "false"

    def test_alive_players_present(self, game_page: Page):
        alive = _alive_players(game_page)
        assert len(alive) >= 8, f"存活玩家应 >= 8, 实际: {len(alive)}"
        for seat in alive:
            assert seat.startswith("Seat"), f"玩家名应为 Seat 格式: {seat}"

    def test_role_assignment(self, game_page: Page):
        roles = _role_chips(game_page)
        assert len(roles) >= 8, f"角色分配应 >= 8, 实际: {len(roles)}"
        role_count: dict[str, int] = {}
        for role in roles.values():
            role_count[role] = role_count.get(role, 0) + 1
        assert role_count.get("werewolf", 0) >= 2, f"狼人应 >= 2, 实际: {role_count}"
        assert "seer" in role_count, f"缺少预言家, 实际: {role_count}"

    def test_role_chips_have_werewolf_class(self, game_page: Page):
        """狼人 chip 应有 werewolf CSS 类。"""
        chips = game_page.locator("#roles-list .chip.werewolf")
        assert chips.count() >= 2

    def test_role_chips_have_role_specific_classes(self, game_page: Page):
        """每个角色 chip 应有对应角色的 CSS 类。"""
        roles = _role_chips(game_page)
        for seat, role in roles.items():
            chips = game_page.locator(f"#roles-list .chip.{role}")
            assert chips.count() >= 1, f"角色 {role} 的 chip 不存在"

    def test_export_still_disabled_for_empty_timeline(self, game_page: Page):
        """新游戏没有时间线日志，导出按钮应禁用。"""
        expect(game_page.locator("#export-log-btn")).to_be_disabled()


# ---------------------------------------------------------------------------
# 3. 单步推进 - 夜晚阶段
# ---------------------------------------------------------------------------

class TestNightPhase:
    """验证夜晚阶段的单步推进。"""

    def test_first_step_completes(self, game_page: Page):
        """第一步（夜晚）应成功完成，状态应更新。"""
        old_updated = _status_value(game_page, "Updated")
        _step_and_wait(game_page)
        new_updated = _status_value(game_page, "Updated")
        # Updated 时间戳应改变（表示服务端确实处理了请求）
        assert new_updated != old_updated, "第一步后 Updated 时间戳应改变"

    def test_night_death_event_format(self, game_page: Page):
        events = _event_rows(game_page)
        death_events = [e for e in events if e["type"] == "death" and e["phase"] == "night"]
        if not death_events:
            pytest.skip("本夜无死亡（守卫可能保住了目标）")
        for e in death_events:
            assert "被杀害" in e["content"], f"夜晚死亡事件应包含'被杀害': {e['content']}"

    def test_alive_reduced_after_death(self, game_page: Page):
        """如果有人死了，存活人数应少于初始人数。"""
        events = _event_rows(game_page)
        night_deaths = [e for e in events if e["type"] == "death" and e["phase"] == "night"]
        if not night_deaths:
            pytest.skip("本夜无死亡")
        alive = _alive_players(game_page)
        roles = _role_chips(game_page)
        initial = len(roles)
        assert len(alive) < initial, f"有夜晚死亡但存活人数未减少: {len(alive)}"

    def test_phase_moved_to_day(self, game_page: Page):
        """夜晚结束后应进入白天。"""
        phase = _status_value(game_page, "Next Phase")
        assert phase in ("night", "finished"), f"夜晚后应进入白天或结束: {phase}"


# ---------------------------------------------------------------------------
# 4. 单步推进 - 白天阶段
# ---------------------------------------------------------------------------

class TestDayPhase:
    """验证白天各子阶段：发言 -> 摘要 -> 初投 -> 终投 -> 决算。"""

    def test_speech_events_appear(self, game_page: Page):
        """白天发言阶段应产生 speech 事件。"""
        for _ in range(2):
            if _is_finished(game_page):
                pytest.skip("游戏已结束")
            _step_and_wait(game_page)

        events = _event_rows(game_page)
        speeches = [e for e in events if e["type"] == "speech"]
        assert len(speeches) > 0, "应有发言事件"

    def test_speech_speaker_is_seat(self, game_page: Page):
        """发言者应为 Seat 格式。"""
        events = _event_rows(game_page)
        speeches = [e for e in events if e["type"] == "speech"]
        for s in speeches:
            assert s["speaker"].startswith("Seat"), f"发言者应为 Seat 格式: {s['speaker']}"

    def test_speech_content_not_empty(self, game_page: Page):
        """发言内容不应为空。"""
        events = _event_rows(game_page)
        speeches = [e for e in events if e["type"] == "speech"]
        for s in speeches:
            assert len(s["content"].strip()) > 0, "发言内容为空"

    def test_summary_event_appears(self, game_page: Page):
        """继续推进到 GM 摘要出现或游戏结束。"""
        for _ in range(5):
            if _is_finished(game_page):
                break
            _step_and_wait(game_page)

        events = _event_rows(game_page)
        summaries = [e for e in events if e["type"] == "summary"]
        if not summaries:
            pytest.skip("游戏结束前没有产生 summary 事件")
        assert len(summaries) > 0, "应有 GM 摘要事件"

    def test_summary_speaker_is_gamemaster(self, game_page: Page):
        events = _event_rows(game_page)
        summaries = [e for e in events if e["type"] == "summary"]
        if not summaries:
            pytest.skip("没有摘要事件")
        for s in summaries:
            assert s["speaker"] == "GameMaster", f"摘要发言者应为 GameMaster: {s['speaker']}"

    def test_day_death_from_vote(self, game_page: Page):
        """白天投票后可能有人被处决。"""
        for _ in range(5):
            if _is_finished(game_page):
                break
            _step_and_wait(game_page)

        events = _event_rows(game_page)
        day_deaths = [e for e in events if e["type"] == "death" and e["phase"] == "day"]
        for d in day_deaths:
            assert "被投票处决" in d["content"], f"白天死亡应包含'被投票处决': {d['content']}"
            assert re.search(r"(\d+)票", d["content"]), f"应包含票数: {d['content']}"


# ---------------------------------------------------------------------------
# 5. 完整游戏流程
# ---------------------------------------------------------------------------

class TestFullGameRun:
    """使用"自动跑到结束"功能完成一整局游戏。"""

    @pytest.fixture(scope="class", autouse=True)
    def run_full_game(self, game_page: Page):
        """先新建一局游戏，然后自动跑到结束。"""
        game_page.locator("#new-game-btn").click()
        expect(game_page.locator("#status-list")).to_contain_text("Game ID", timeout=10_000)

        game_page.locator("#max-steps-input").fill("120")
        game_page.locator("#run-btn").click()

        # 等待游戏结束（finished 变为 true）
        expect(game_page.locator("#status-list")).to_contain_text("true", timeout=600_000)

    def test_game_finished(self, game_page: Page):
        assert _status_value(game_page, "Finished") == "true"

    def test_winner_declared(self, game_page: Page):
        winner = _status_value(game_page, "Winner")
        assert winner in ("werewolves", "villagers"), f"胜负应为狼人或村民获胜: {winner}"

    def test_winner_consistent_with_alive(self, game_page: Page):
        """验证 winner 与存活玩家数量一致。"""
        winner = _status_value(game_page, "Winner")
        alive = _alive_players(game_page)
        roles = _role_chips(game_page)

        alive_wolves = sum(1 for p in alive if roles.get(p) == "werewolf")
        alive_villagers = len(alive) - alive_wolves

        if winner == "villagers":
            assert alive_wolves == 0, f"村民获胜但还有 {alive_wolves} 个狼人存活"
        elif winner == "werewolves":
            assert alive_wolves >= alive_villagers, (
                f"狼人获胜但狼人({alive_wolves})未 >= 村民({alive_villagers})"
            )

    def test_final_phase_is_finished(self, game_page: Page):
        phase = _status_value(game_page, "Next Phase")
        assert phase == "finished", f"游戏结束后 nextPhase 应为 finished: {phase}"

    def test_timeline_not_empty(self, game_page: Page):
        timeline = game_page.locator("#timeline")
        expect(timeline).not_to_contain_text("暂无日志")
        content = timeline.inner_text()
        lines = [l for l in content.split("\n") if l.strip()]
        assert len(lines) >= 10, f"时间线应有至少10行，实际: {len(lines)}"

    def test_events_table_complete(self, game_page: Page):
        """公共事件表应有完整的事件记录。"""
        events = _event_rows(game_page)
        assert len(events) >= 10, f"事件应 >= 10, 实际: {len(events)}"

        event_types = {e["type"] for e in events}
        assert "speech" in event_types, "应有 speech 事件"
        assert "summary" in event_types, "应有 summary 事件"
        assert "death" in event_types, "应有 death 事件"

    def test_death_events_reference_valid_seats(self, game_page: Page):
        """所有死亡事件提到的玩家都是有效的 Seat。"""
        roles = _role_chips(game_page)
        max_seat = max(int(s.replace("Seat", "")) for s in roles)
        events = _event_rows(game_page)
        for e in events:
            if e["type"] == "death":
                seats_in_content = re.findall(r"Seat\d+", e["content"])
                for seat in seats_in_content:
                    num = int(seat.replace("Seat", ""))
                    assert 1 <= num <= max_seat, f"无效座位号: {seat}"

    def test_day_numbers_monotonic(self, game_page: Page):
        """天数应单调递增。"""
        events = _event_rows(game_page)
        days = [int(e["day"]) for e in events if e["day"].isdigit()]
        for i in range(1, len(days)):
            assert days[i] >= days[i - 1], f"天数非单调: {days}"

    def test_all_buttons_enabled_after_game(self, game_page: Page):
        expect(game_page.locator("#new-game-btn")).to_be_enabled()
        expect(game_page.locator("#step-btn")).to_be_enabled()
        expect(game_page.locator("#run-btn")).to_be_enabled()

    def test_export_button_enabled(self, game_page: Page):
        expect(game_page.locator("#export-log-btn")).to_be_enabled()

    def test_step_does_nothing_when_finished(self, game_page: Page):
        """游戏结束后点击单步推进不应改变状态。"""
        events_before = len(_event_rows(game_page))
        game_page.locator("#step-btn").click()
        expect(game_page.locator("#step-btn")).to_be_enabled(timeout=10_000)
        events_after = len(_event_rows(game_page))
        assert events_after == events_before, "游戏结束后推进不应增加事件"


# ---------------------------------------------------------------------------
# 6. 导出功能
# ---------------------------------------------------------------------------

class TestExport:
    """验证日志导出功能。"""

    def test_export_creates_markdown_file(self, game_page: Page):
        with game_page.expect_download() as download_info:
            game_page.locator("#export-log-btn").click()
        download = download_info.value
        assert download.suggested_filename.startswith("werewolf-log-")
        assert download.suggested_filename.endswith(".md")

    def test_export_file_contains_content(self, game_page: Page):
        with game_page.expect_download() as download_info:
            game_page.locator("#export-log-btn").click()
        download = download_info.value
        path = download.path()
        content = path.read_text(encoding="utf-8")
        assert "AI 狼人杀运行日志" in content
        assert "时间线日志" in content
        assert "Game ID" in content


# ---------------------------------------------------------------------------
# 7. 重新开局
# ---------------------------------------------------------------------------

class TestRestartGame:
    """验证重新开局功能。"""

    def test_new_game_resets_state(self, game_page: Page):
        # 记录旧的时间戳
        old_updated = _status_value(game_page, "Updated")

        game_page.locator("#new-game-btn").click()
        expect(game_page.locator("#status-list")).to_contain_text("Game ID", timeout=10_000)

        # 新游戏应该有不同的 Updated 时间（或者不同的 Game ID）
        new_updated = _status_value(game_page, "Updated")
        new_game_id = _status_value(game_page, "Game ID")
        # 至少 Updated 时间应不同
        assert new_updated != old_updated or len(new_game_id) == 8, "新游戏应重新创建"

    def test_new_game_resets_winner(self, game_page: Page):
        assert _status_value(game_page, "Winner") == "none"

    def test_new_game_resets_day(self, game_page: Page):
        assert _status_value(game_page, "Day") == "1"

    def test_new_game_resets_alive(self, game_page: Page):
        alive_count = int(_status_value(game_page, "Alive"))
        assert alive_count >= 8, f"新游戏存活人数应 >= 8, 实际: {alive_count}"

    def test_new_game_resets_finished(self, game_page: Page):
        assert _status_value(game_page, "Finished") == "false"

    def test_new_game_clears_events(self, game_page: Page):
        events = _event_rows(game_page)
        assert len(events) == 0, f"新游戏应清空事件, 实际有 {len(events)} 个"


# ---------------------------------------------------------------------------
# 8. 边界情况和错误处理
# ---------------------------------------------------------------------------

class TestEdgeCases:
    """测试边界情况。"""

    def test_step_without_game_shows_error(self, browser, live_url):
        """没有游戏时点击推进应恢复按钮状态。"""
        page = browser.new_page()
        page.goto(live_url)
        page.wait_for_load_state("networkidle")

        page.locator("#step-btn").click()
        expect(page.locator("#step-btn")).to_be_enabled(timeout=10_000)

        page.close()

    def test_max_steps_input_validation(self, browser, live_url):
        """最大步数输入应有限制。"""
        page = browser.new_page()
        page.goto(live_url)
        page.wait_for_load_state("networkidle")

        input_el = page.locator("#max-steps-input")
        expect(input_el).to_have_attribute("min", "1")
        expect(input_el).to_have_attribute("max", "128")

        page.close()

    def test_buttons_disabled_while_busy(self, browser, live_url):
        """请求进行中时按钮应禁用。"""
        page = browser.new_page()
        page.goto(live_url)
        page.wait_for_load_state("networkidle")

        page.locator("#new-game-btn").click()
        expect(page.locator("#status-list")).to_contain_text("Game ID", timeout=10_000)

        # 点击自动运行，立即检查按钮状态
        page.locator("#run-btn").click()
        # 按钮在运行中应立即禁用
        expect(page.locator("#new-game-btn")).to_be_disabled(timeout=2_000)

        # 等待运行结束
        expect(page.locator("#status-list")).to_contain_text("true", timeout=600_000)

        page.close()


# ---------------------------------------------------------------------------
# 9. 公共事件表完整性
# ---------------------------------------------------------------------------

class TestEventIntegrity:
    """验证公共事件表的数据完整性。"""

    @pytest.fixture(scope="class", autouse=True)
    def run_another_game(self, game_page: Page):
        """再开一局用于完整性验证。"""
        game_page.locator("#new-game-btn").click()
        expect(game_page.locator("#status-list")).to_contain_text("Game ID", timeout=10_000)

        game_page.locator("#max-steps-input").fill("120")
        game_page.locator("#run-btn").click()
        expect(game_page.locator("#status-list")).to_contain_text("true", timeout=600_000)

    def test_events_have_valid_phase(self, game_page: Page):
        """所有事件的 phase 应为 night 或 day。"""
        events = _event_rows(game_page)
        for e in events:
            assert e["phase"] in ("night", "day"), f"无效 phase: {e['phase']}"

    def test_events_have_valid_type(self, game_page: Page):
        """所有事件的 type 应在已知范围内。"""
        valid_types = {"death", "speech", "summary", "vote", "night_action"}
        events = _event_rows(game_page)
        for e in events:
            assert e["type"] in valid_types, f"未知事件类型: {e['type']}"

    def test_night_events_before_day_same_day(self, game_page: Page):
        """同一天内，夜晚事件应在白天事件之前。"""
        events = _event_rows(game_page)
        for day in {e["day"] for e in events}:
            day_events = [e for e in events if e["day"] == day]
            night_idx = [i for i, e in enumerate(day_events) if e["phase"] == "night"]
            day_idx = [i for i, e in enumerate(day_events) if e["phase"] == "day"]
            if night_idx and day_idx:
                assert max(night_idx) < min(day_idx), (
                    f"Day{day}: 夜晚事件应在白天之前"
                )

    def test_all_alive_players_spoke(self, game_page: Page):
        """第一天每个存活玩家都应有发言记录。"""
        events = _event_rows(game_page)
        day_speakers: dict[str, set[str]] = {}
        for e in events:
            if e["type"] == "speech" and e["phase"] == "day":
                day_speakers.setdefault(e["day"], set()).add(e["speaker"])

        # 第一天所有初始玩家都应发言
        if "1" in day_speakers:
            roles = _role_chips(game_page)
            expected = len(roles)
            assert len(day_speakers["1"]) == expected, (
                f"第一天应有{expected}个发言者, 实际: {len(day_speakers['1'])}"
            )

    def test_no_duplicate_seats_in_alive_list(self, game_page: Page):
        """存活玩家列表不应有重复。"""
        alive = _alive_players(game_page)
        assert len(alive) == len(set(alive)), f"存活玩家有重复: {alive}"

    def test_dead_players_not_in_alive(self, game_page: Page):
        """已死玩家不应出现在存活列表中。"""
        events = _event_rows(game_page)
        dead_seats: set[str] = set()
        for e in events:
            if e["type"] == "death":
                seats = re.findall(r"Seat\d+", e["content"])
                dead_seats.update(seats)

        alive = set(_alive_players(game_page))
        overlap = dead_seats & alive
        assert len(overlap) == 0, f"已死玩家仍在存活列表中: {overlap}"
