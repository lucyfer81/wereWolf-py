"""完整的9人局（经典局）狼人杀 Playwright E2E 测试。

角色配置: 3狼人 + 预言家 + 女巫 + 守卫 + 3村民 = 9人
女巫特殊能力: 解药（救人）+ 毒药（毒人），各只能用一次

通过拦截 /api/game/new 请求的 config_path 参数来指定 classic-9p.yaml 配置。

覆盖范围:
- 9人局新建游戏与角色分配（含女巫）
- 单步推进夜晚/白天阶段
- 自动跑完全局
- 胜负判定一致性
- 事件表完整性（夜晚/白天顺序、发言人数）
- 导出 Markdown
- 重新开局
"""

from __future__ import annotations

import json
import re

import pytest
from playwright.sync_api import Page, Route, expect


STEP_TIMEOUT = 120_000
CONFIG_FILE = "classic-9p.yaml"


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

def _intercept_new_game(route: Route):
    """拦截 /api/game/new 请求，注入 config_path 参数。"""
    route.continue_(post_data=json.dumps({"config_path": CONFIG_FILE}))


def _create_9p_game(page: Page):
    """通过拦截请求创建一局9人局游戏。"""
    page.route("**/api/game/new", _intercept_new_game)
    page.locator("#new-game-btn").click()
    expect(page.locator("#status-list")).to_contain_text("Game ID", timeout=10_000)
    page.unroute("**/api/game/new")


def _status_value(page: Page, key: str) -> str:
    rows = page.locator("#status-list div")
    for i in range(rows.count()):
        row = rows.nth(i)
        dt = row.locator("dt")
        if dt.inner_text().strip() == key:
            return row.locator("dd").inner_text().strip()
    return ""


def _alive_players(page: Page) -> list[str]:
    chips = page.locator("#alive-list .chip")
    return [chips.nth(i).inner_text() for i in range(chips.count())]


def _event_rows(page: Page) -> list[dict]:
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
    chips = page.locator("#roles-list .chip")
    roles = {}
    for i in range(chips.count()):
        text = chips.nth(i).inner_text()
        parts = text.split("·")
        if len(parts) == 2:
            roles[parts[0].strip()] = parts[1].strip()
    return roles


def _is_finished(page: Page) -> bool:
    return _status_value(page, "Finished") == "true"


def _step_and_wait(page: Page, timeout: float = STEP_TIMEOUT):
    page.locator("#step-btn").click()
    expect(page.locator("#step-btn")).to_be_enabled(timeout=timeout)
    page.wait_for_timeout(200)


# ---------------------------------------------------------------------------
# 1. 页面加载
# ---------------------------------------------------------------------------

class TestPageLoad:
    def test_title(self, game_page: Page):
        expect(game_page).to_have_title(re.compile(r"Werewolf"))

    def test_header_visible(self, game_page: Page):
        expect(game_page.locator("h1")).to_contain_text("Werewolf AI Arena")

    def test_control_buttons(self, game_page: Page):
        expect(game_page.locator("#new-game-btn")).to_be_visible()
        expect(game_page.locator("#step-btn")).to_be_visible()
        expect(game_page.locator("#run-btn")).to_be_visible()
        expect(game_page.locator("#max-steps-input")).to_be_visible()

    def test_initial_no_events(self, game_page: Page):
        expect(game_page.locator("#events-body")).to_contain_text("暂无公共事件")

    def test_export_disabled(self, game_page: Page):
        expect(game_page.locator("#export-log-btn")).to_be_disabled()


# ---------------------------------------------------------------------------
# 2. 新建9人局
# ---------------------------------------------------------------------------

class TestNewGame9P:
    """验证9人局角色分配: 3狼 + 预言家 + 女巫 + 守卫 + 3村民 = 9。"""

    def test_create_9p_game(self, game_page: Page):
        _create_9p_game(game_page)

    def test_9_alive_players(self, game_page: Page):
        alive = _alive_players(game_page)
        assert len(alive) == 9, f"9人局应有9个存活玩家, 实际: {len(alive)}"
        assert alive == [f"Seat{i}" for i in range(1, 10)]

    def test_alive_count_status(self, game_page: Page):
        assert _status_value(game_page, "Alive") == "9"

    def test_role_count(self, game_page: Page):
        roles = _role_chips(game_page)
        assert len(roles) == 9
        rc: dict[str, int] = {}
        for r in roles.values():
            rc[r] = rc.get(r, 0) + 1
        assert rc == {"werewolf": 3, "seer": 1, "witch": 1, "guard": 1, "villager": 3}, \
            f"角色分配不符: {rc}"

    def test_witch_role_present(self, game_page: Page):
        """9人局必须有女巫。"""
        roles = _role_chips(game_page)
        witch_seats = [s for s, r in roles.items() if r == "witch"]
        assert len(witch_seats) == 1, f"应有1个女巫, 实际: {witch_seats}"

    def test_witch_chip_has_css_class(self, game_page: Page):
        """女巫 chip 应有 witch CSS 类。"""
        assert game_page.locator("#roles-list .chip.witch").count() == 1

    def test_all_role_chips_have_class(self, game_page: Page):
        roles = _role_chips(game_page)
        for seat, role in roles.items():
            assert game_page.locator(f"#roles-list .chip.{role}").count() >= 1, \
                f"角色 {role} 缺少 CSS 类"

    def test_initial_state(self, game_page: Page):
        assert _status_value(game_page, "Day") == "1"
        assert _status_value(game_page, "Winner") == "none"
        assert _status_value(game_page, "Finished") == "false"


# ---------------------------------------------------------------------------
# 3. 夜晚阶段
# ---------------------------------------------------------------------------

class TestNightPhase:
    def test_first_step_completes(self, game_page: Page):
        old_updated = _status_value(game_page, "Updated")
        _step_and_wait(game_page)
        assert _status_value(game_page, "Updated") != old_updated

    def test_night_death_format(self, game_page: Page):
        events = _event_rows(game_page)
        deaths = [e for e in events if e["type"] == "death" and e["phase"] == "night"]
        if not deaths:
            pytest.skip("本夜无死亡（守卫/女巫可能救了目标）")
        for d in deaths:
            assert "被杀害" in d["content"], f"夜晚死亡格式错误: {d['content']}"

    def test_alive_reduced_or_saved(self, game_page: Page):
        """夜晚后存活人数要么减少，要么不变（被救了）。"""
        events = _event_rows(game_page)
        night_deaths = [e for e in events if e["type"] == "death" and e["phase"] == "night"]
        alive = _alive_players(game_page)
        if night_deaths:
            assert len(alive) < 9, f"有死亡但存活人数未减少: {len(alive)}"
        else:
            # 无死亡 = 守卫或女巫救了人
            assert len(alive) == 9

    def test_phase_moved_to_day(self, game_page: Page):
        phase = _status_value(game_page, "Next Phase")
        assert phase in ("night", "finished"), f"夜晚后阶段错误: {phase}"


# ---------------------------------------------------------------------------
# 4. 白天阶段
# ---------------------------------------------------------------------------

class TestDayPhase:
    def test_speech_events(self, game_page: Page):
        for _ in range(2):
            if _is_finished(game_page):
                pytest.skip("游戏已结束")
            _step_and_wait(game_page)
        speeches = [e for e in _event_rows(game_page) if e["type"] == "speech"]
        assert len(speeches) > 0, "应有发言事件"

    def test_speech_format(self, game_page: Page):
        for e in _event_rows(game_page):
            if e["type"] == "speech":
                assert e["speaker"].startswith("Seat")
                assert len(e["content"].strip()) > 0

    def test_summary_or_skip(self, game_page: Page):
        for _ in range(5):
            if _is_finished(game_page):
                break
            _step_and_wait(game_page)
        summaries = [e for e in _event_rows(game_page) if e["type"] == "summary"]
        if not summaries:
            pytest.skip("游戏提前结束，无摘要")
        assert summaries[0]["speaker"] == "GameMaster"

    def test_vote_death_format(self, game_page: Page):
        for _ in range(5):
            if _is_finished(game_page):
                break
            _step_and_wait(game_page)
        day_deaths = [e for e in _event_rows(game_page)
                      if e["type"] == "death" and e["phase"] == "day"]
        for d in day_deaths:
            assert "被投票处决" in d["content"]
            assert re.search(r"(\d+)票", d["content"])


# ---------------------------------------------------------------------------
# 5. 完整游戏
# ---------------------------------------------------------------------------

class TestFullGameRun:
    @pytest.fixture(scope="class", autouse=True)
    def run_full_game(self, game_page: Page):
        _create_9p_game(game_page)
        game_page.locator("#max-steps-input").fill("150")
        game_page.locator("#run-btn").click()
        expect(game_page.locator("#status-list")).to_contain_text("true", timeout=600_000)

    def test_finished(self, game_page: Page):
        assert _status_value(game_page, "Finished") == "true"

    def test_winner(self, game_page: Page):
        winner = _status_value(game_page, "Winner")
        assert winner in ("werewolves", "villagers"), f"无效 winner: {winner}"

    def test_winner_consistent(self, game_page: Page):
        winner = _status_value(game_page, "Winner")
        alive = _alive_players(game_page)
        roles = _role_chips(game_page)
        wolves = sum(1 for p in alive if roles.get(p) == "werewolf")
        villagers = len(alive) - wolves

        if winner == "villagers":
            assert wolves == 0, f"村民获胜但还有 {wolves} 狼人"
        else:
            assert wolves >= villagers, f"狼人获胜但狼({wolves}) < 村民({villagers})"

    def test_final_phase(self, game_page: Page):
        assert _status_value(game_page, "Next Phase") == "finished"

    def test_timeline_rich(self, game_page: Page):
        tl = game_page.locator("#timeline")
        expect(tl).not_to_contain_text("暂无日志")
        lines = [l for l in tl.inner_text().split("\n") if l.strip()]
        assert len(lines) >= 10

    def test_events_types(self, game_page: Page):
        events = _event_rows(game_page)
        assert len(events) >= 10
        types = {e["type"] for e in events}
        assert "speech" in types
        assert "summary" in types
        assert "death" in types

    def test_death_seats_valid(self, game_page: Page):
        roles = _role_chips(game_page)
        max_seat = max(int(s.replace("Seat", "")) for s in roles)
        for e in _event_rows(game_page):
            if e["type"] == "death":
                for seat in re.findall(r"Seat\d+", e["content"]):
                    assert 1 <= int(seat.replace("Seat", "")) <= max_seat

    def test_day_monotonic(self, game_page: Page):
        days = [int(e["day"]) for e in _event_rows(game_page) if e["day"].isdigit()]
        for i in range(1, len(days)):
            assert days[i] >= days[i - 1]

    def test_step_noop_after_finish(self, game_page: Page):
        before = len(_event_rows(game_page))
        game_page.locator("#step-btn").click()
        expect(game_page.locator("#step-btn")).to_be_enabled(timeout=10_000)
        assert len(_event_rows(game_page)) == before

    def test_export_enabled(self, game_page: Page):
        expect(game_page.locator("#export-log-btn")).to_be_enabled()


# ---------------------------------------------------------------------------
# 6. 导出
# ---------------------------------------------------------------------------

class TestExport:
    def test_download_md(self, game_page: Page):
        with game_page.expect_download() as di:
            game_page.locator("#export-log-btn").click()
        dl = di.value
        assert dl.suggested_filename.startswith("werewolf-log-")
        assert dl.suggested_filename.endswith(".md")

    def test_md_content(self, game_page: Page):
        with game_page.expect_download() as di:
            game_page.locator("#export-log-btn").click()
        content = di.value.path().read_text(encoding="utf-8")
        assert "AI 狼人杀运行日志" in content
        assert "Game ID" in content


# ---------------------------------------------------------------------------
# 7. 重新开局（9人局）
# ---------------------------------------------------------------------------

class TestRestart9P:
    def test_restart_creates_new_9p_game(self, game_page: Page):
        old_updated = _status_value(game_page, "Updated")
        _create_9p_game(game_page)
        assert _status_value(game_page, "Updated") != old_updated

    def test_restart_9_players(self, game_page: Page):
        assert int(_status_value(game_page, "Alive")) == 9
        assert len(_alive_players(game_page)) == 9

    def test_restart_role_count(self, game_page: Page):
        roles = _role_chips(game_page)
        rc: dict[str, int] = {}
        for r in roles.values():
            rc[r] = rc.get(r, 0) + 1
        assert rc == {"werewolf": 3, "seer": 1, "witch": 1, "guard": 1, "villager": 3}

    def test_restart_winner_reset(self, game_page: Page):
        assert _status_value(game_page, "Winner") == "none"

    def test_restart_events_cleared(self, game_page: Page):
        assert len(_event_rows(game_page)) == 0


# ---------------------------------------------------------------------------
# 8. 事件完整性（再跑一局9人局）
# ---------------------------------------------------------------------------

class TestEventIntegrity:
    @pytest.fixture(scope="class", autouse=True)
    def run_final_game(self, game_page: Page):
        _create_9p_game(game_page)
        game_page.locator("#max-steps-input").fill("150")
        game_page.locator("#run-btn").click()
        expect(game_page.locator("#status-list")).to_contain_text("true", timeout=600_000)

    def test_valid_phases(self, game_page: Page):
        for e in _event_rows(game_page):
            assert e["phase"] in ("night", "day"), f"无效 phase: {e['phase']}"

    def test_valid_types(self, game_page: Page):
        valid = {"death", "speech", "summary", "vote", "night_action"}
        for e in _event_rows(game_page):
            assert e["type"] in valid, f"未知类型: {e['type']}"

    def test_night_before_day(self, game_page: Page):
        events = _event_rows(game_page)
        for day in {e["day"] for e in events}:
            de = [e for e in events if e["day"] == day]
            ni = [i for i, e in enumerate(de) if e["phase"] == "night"]
            di = [i for i, e in enumerate(de) if e["phase"] == "day"]
            if ni and di:
                assert max(ni) < min(di), f"Day{day}: 夜晚应在白天前"

    def test_all_players_spoke_day1(self, game_page: Page):
        speakers: set[str] = set()
        for e in _event_rows(game_page):
            if e["type"] == "speech" and e["phase"] == "day" and e["day"] == "1":
                speakers.add(e["speaker"])
        assert len(speakers) == 9, f"第一天应有9人发言, 实际: {len(speakers)}"

    def test_no_duplicate_alive(self, game_page: Page):
        alive = _alive_players(game_page)
        assert len(alive) == len(set(alive))

    def test_dead_not_alive(self, game_page: Page):
        dead: set[str] = set()
        for e in _event_rows(game_page):
            if e["type"] == "death":
                dead.update(re.findall(r"Seat\d+", e["content"]))
        alive = set(_alive_players(game_page))
        assert not (dead & alive), f"死者仍在存活列表: {dead & alive}"

    def test_witch_role_in_final_game(self, game_page: Page):
        """最终一局仍然要有女巫角色。"""
        roles = _role_chips(game_page)
        assert "witch" in roles.values(), f"缺少女巫: {roles}"
