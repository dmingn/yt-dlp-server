from collections.abc import Callable
from contextlib import AbstractContextManager

from playwright.sync_api import Page, expect

LiveServer = Callable[..., AbstractContextManager[str]]


def test_index_shows_empty_jobs(page: Page, live_server: LiveServer) -> None:
    # Act
    with live_server(yt_dlp_cmd=("sleep", "0")) as url:
        page.goto(url)

        # Assert
        expect(page.get_by_role("heading", name="yt-dlp-server")).to_be_visible()
        expect(page.locator("#url-input")).to_be_visible()
        expect(page.locator("#jobs")).to_contain_text("No jobs yet.")


def test_submit_job_shows_selected_job_with_log(
    page: Page, live_server: LiveServer
) -> None:
    with live_server(yt_dlp_cmd=("sleep", "0")) as url:
        # Arrange
        page.goto(url)

        # Act
        page.locator("#url-input").fill("https://example.com/video")
        page.locator("#submit-btn").click()

        # Assert
        expect(page.locator("#url-input")).to_have_value("")
        article = page.locator("#jobs article.selected")
        expect(article).to_be_visible()
        expect(article).to_contain_text("https://example.com/video")
        expect(article.locator(".status")).to_be_visible()
        expect(article.get_by_role("button", name="Copy log")).to_be_visible()
        expect(article.locator("pre")).to_be_visible()


def test_job_log_follows_tail_and_keeps_manual_scroll(
    page: Page, live_server: LiveServer
) -> None:
    with live_server(
        yt_dlp_cmd=(
            "python",
            "-c",
            "print('\\n'.join(str(i) for i in range(200)))",
        )
    ) as url:
        # Arrange
        page.goto(url)
        page.locator("#url-input").fill("https://example.com/video")
        page.locator("#submit-btn").click()
        pre = page.locator("#jobs article.selected pre")
        expect(pre).to_contain_text("199")
        page.wait_for_function(
            """() => {
              const el = document.querySelector("#jobs article.selected pre");
              return el && el.scrollHeight > el.clientHeight + 40;
            }"""
        )

        # Assert: opening a log pins to the latest lines
        assert page.evaluate(
            """() => {
              const el = document.querySelector("#jobs article.selected pre");
              return el.scrollHeight - el.clientHeight - el.scrollTop < 24;
            }"""
        )

        # Act: scroll away from the tail, then wait for the 2s poll redraw
        page.evaluate(
            """() => {
              const el = document.querySelector("#jobs article.selected pre");
              el.dataset.seen = "1";
              el.scrollTop = 80;
            }"""
        )
        page.wait_for_function(
            """() => {
              const el = document.querySelector("#jobs article.selected pre");
              return el && el.dataset.seen !== "1";
            }"""
        )

        # Assert: a redraw must not jump back to the top
        scroll_top = page.evaluate(
            """() => document.querySelector("#jobs article.selected pre").scrollTop"""
        )
        assert 50 <= scroll_top <= 110


def test_cancel_button_cancels_job(page: Page, live_server: LiveServer) -> None:
    # UI covers the cancel control end-to-end once; queued vs running cancel
    # semantics are asserted in the API tests.
    with live_server(yt_dlp_cmd=("sleep", "60")) as url:
        # Arrange
        page.goto(url)
        page.locator("#url-input").fill("https://example.com/video")
        page.locator("#submit-btn").click()
        article = page.locator("#jobs article").first
        expect(article.get_by_role("button", name="Cancel")).to_be_visible()

        # Act
        article.get_by_role("button", name="Cancel").click()

        # Assert
        expect(article.locator(".status")).to_have_text("cancelled")
        expect(article.get_by_role("button", name="Cancel")).to_have_count(0)


def test_submit_invalid_url_shows_form_error(
    page: Page, live_server: LiveServer
) -> None:
    with live_server(yt_dlp_cmd=("sleep", "0")) as url:
        # Arrange: disable form validation (noValidate) so type=url does not block
        # submit and the API error path can populate #form-error
        page.goto(url)
        page.locator("#submit-form").evaluate("form => { form.noValidate = true; }")

        # Act
        page.locator("#url-input").fill("not-a-url")
        page.locator("#submit-btn").click()

        # Assert
        error = page.locator("#form-error")
        expect(error).to_be_visible()
        expect(error).to_contain_text("Invalid URL")
        expect(page.locator("#jobs")).to_contain_text("No jobs yet.")


def test_schedules_view_creates_and_cancels_schedule(
    page: Page, live_server: LiveServer
) -> None:
    with live_server(yt_dlp_cmd=("sleep", "60")) as url:
        # Arrange
        page.goto(url)
        page.get_by_role("link", name="Schedules").click()
        expect(page.locator("#schedule-tz-hint")).to_contain_text("local timezone")
        expect(page.locator("#schedules")).to_contain_text("No schedules yet.")

        # Act
        page.locator("#schedule-url-input").fill("https://example.com/live")
        page.locator("#schedule-at-input").fill("2099-01-01T12:00")
        page.locator("#schedule-btn").click()

        # Assert
        article = page.locator("#schedules article").first
        expect(article).to_contain_text("https://example.com/live")
        expect(article.locator(".status")).to_have_text("scheduled")
        expect(page.locator("#jobs")).to_contain_text("No jobs yet.")

        # Act
        article.get_by_role("button", name="Cancel").click()

        # Assert
        expect(page.locator("#schedules")).to_contain_text("No schedules yet.")


def test_schedule_save_updates_time(page: Page, live_server: LiveServer) -> None:
    with live_server(yt_dlp_cmd=("sleep", "60")) as url:
        # Arrange
        page.goto(url + "#schedules")
        page.locator("#schedule-url-input").fill("https://example.com/live")
        page.locator("#schedule-at-input").fill("2099-01-01T12:00")
        page.locator("#schedule-btn").click()
        article = page.locator("#schedules article").first
        expect(article).to_be_visible()

        # Act
        at_input = article.locator('input[type="datetime-local"]')
        at_input.fill("2099-06-01T18:30")
        at_input.focus()
        page.wait_for_timeout(2500)
        expect(at_input).to_have_value("2099-06-01T18:30")
        article.get_by_role("button", name="Save").click()

        # Assert
        expect(article.locator('input[type="datetime-local"]')).to_have_value(
            "2099-06-01T18:30"
        )
