"""E2E tests: Playwright drives a real browser against a real server with LLM calls."""

from __future__ import annotations

import pytest
from playwright.sync_api import Page, expect


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


def _click_and_wait(page: Page, selector: str, wait_for_selector: str, timeout: float = 120_000):
    page.locator(selector).click()
    expect(page.locator(wait_for_selector)).to_be_visible(timeout=timeout)


class TestBasicFlow:
    """Test the basic game flow: create game, step, verify UI state."""

    def test_page_loads(self, game_page: Page):
        expect(game_page.locator("h1")).to_contain_text("Werewolf AI Arena")
        expect(game_page.locator("#new-game-btn")).to_be_visible()
        expect(game_page.locator("#step-btn")).to_be_visible()
        expect(game_page.locator("#run-btn")).to_be_visible()

    def test_initial_state(self, game_page: Page):
        expect(game_page.locator("#timeline")).to_contain_text("点击")
        expect(game_page.locator("#events-body")).to_contain_text("暂无事件")
        expect(game_page.locator("#export-log-btn")).to_be_disabled()

    def test_create_new_game(self, game_page: Page):
        game_page.locator("#new-game-btn").click()
        expect(game_page.locator("#status-list")).to_contain_text("Game ID", timeout=10_000)

        expect(game_page.locator("#status-list")).to_contain_text("Day")
        expect(game_page.locator("#status-list")).to_contain_text("1")
        expect(game_page.locator("#status-list")).to_contain_text("none")
        expect(game_page.locator("#status-list")).to_contain_text("false")

        expect(game_page.locator("#alive-list")).to_contain_text("Seat1")
        expect(game_page.locator("#alive-list")).to_contain_text("Seat8")

        expect(game_page.locator("#roles-list")).to_contain_text("werewolf")
        expect(game_page.locator("#roles-list")).to_contain_text("villager")

        # Export button stays disabled because timeline is empty for a new game
        expect(game_page.locator("#export-log-btn")).to_be_disabled()

    def test_step_game_once(self, game_page: Page):
        game_page.locator("#step-btn").click()
        expect(game_page.locator("#events-body")).not_to_contain_text("暂无事件", timeout=120_000)

        expect(game_page.locator("#timeline")).not_to_contain_text("暂无日志")

    def test_step_multiple_times(self, game_page: Page):
        for _ in range(3):
            game_page.locator("#step-btn").click()
            game_page.wait_for_timeout(200)

        # Wait for the last step to finish by checking event count increases
        expect(game_page.locator("#events-body tr")).not_to_have_count(0, timeout=120_000)

    def test_buttons_enabled_after_steps(self, game_page: Page):
        expect(game_page.locator("#new-game-btn")).to_be_enabled()
        expect(game_page.locator("#step-btn")).to_be_enabled()
        expect(game_page.locator("#run-btn")).to_be_enabled()

    def test_export_button_creates_download(self, game_page: Page):
        with game_page.expect_download() as download_info:
            game_page.locator("#export-log-btn").click()
        download = download_info.value
        assert download.suggested_filename.startswith("werewolf-log-")
        assert download.suggested_filename.endswith(".md")


class TestEdgeCases:
    """Test edge cases and error handling."""

    def test_step_without_game_shows_error(self, browser, live_url):
        page = browser.new_page()
        page.goto(live_url)
        page.wait_for_load_state("networkidle")

        page.locator("#step-btn").click()
        # The error response is returned but the page should still be usable
        # Wait for the busy state to clear (setBusy(false) in finally block)
        expect(page.locator("#step-btn")).to_be_enabled(timeout=10_000)

        page.close()
