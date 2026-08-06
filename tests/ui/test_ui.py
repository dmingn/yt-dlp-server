from playwright.sync_api import Page, expect


def test_index_shows_empty_jobs(page: Page, live_server_url: str) -> None:
    # Act
    page.goto(live_server_url)

    # Assert
    expect(page.get_by_role("heading", name="yt-dlp-server")).to_be_visible()
    expect(page.locator("#url-input")).to_be_visible()
    expect(page.locator("#jobs")).to_contain_text("No jobs yet.")


def test_submit_job_shows_selected_job_with_log(
    page: Page, live_server_url: str
) -> None:
    # Arrange
    page.goto(live_server_url)

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


def test_submit_invalid_url_shows_form_error(page: Page, live_server_url: str) -> None:
    # Arrange: disable form validation (noValidate) so type=url does not block
    # submit and the API error path can populate #form-error
    page.goto(live_server_url)
    page.locator("#submit-form").evaluate("form => { form.noValidate = true; }")

    # Act
    page.locator("#url-input").fill("not-a-url")
    page.locator("#submit-btn").click()

    # Assert
    error = page.locator("#form-error")
    expect(error).to_be_visible()
    expect(error).to_contain_text("Invalid URL")
    expect(page.locator("#jobs")).to_contain_text("No jobs yet.")
