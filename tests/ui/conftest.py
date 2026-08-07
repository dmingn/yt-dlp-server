import socket
import threading
import time
from collections.abc import Iterator
from contextlib import AbstractContextManager, contextmanager
from typing import Protocol

import httpx
import pytest
import uvicorn
from playwright.sync_api import Page, sync_playwright

from yt_dlp_server.app import create_app
from yt_dlp_server.settings import Settings


class LiveServerFactory(Protocol):
    def __call__(
        self, *, block_seconds: int = 0
    ) -> AbstractContextManager[str]: ...


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


@pytest.fixture
def live_server(monkeypatch: pytest.MonkeyPatch) -> LiveServerFactory:
    @contextmanager
    def _start(*, block_seconds: int = 0) -> Iterator[str]:
        monkeypatch.setattr(
            "yt_dlp_server.worker.build_yt_dlp_cmd",
            lambda **kwargs: ("sleep", str(block_seconds)),
        )
        app = create_app(Settings(n_workers=1))
        port = _free_port()
        config = uvicorn.Config(
            app,
            host="127.0.0.1",
            port=port,
            log_level="warning",
            access_log=False,
        )
        server = uvicorn.Server(config)
        thread = threading.Thread(target=server.run, daemon=True)
        thread.start()

        url = f"http://127.0.0.1:{port}"
        deadline = time.monotonic() + 10
        while time.monotonic() < deadline:
            if server.started:
                try:
                    response = httpx.get(url, timeout=0.5)
                    if response.status_code == 200:
                        break
                except httpx.HTTPError:
                    pass
            time.sleep(0.05)
        else:
            server.should_exit = True
            thread.join(timeout=5)
            raise RuntimeError(f"UI test server failed to start at {url}")

        try:
            yield url
        finally:
            server.should_exit = True
            thread.join(timeout=5)

    return _start


@pytest.fixture
def page() -> Iterator[Page]:
    # Function-scoped Playwright so the sync API event loop does not outlive
    # the test and break pytest-asyncio worker tests in the same session.
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch()
        context = browser.new_context()
        yield context.new_page()
        context.close()
        browser.close()
