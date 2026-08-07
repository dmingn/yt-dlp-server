import time
from collections.abc import Iterator
from typing import Any

import pytest
from fastapi.testclient import TestClient

from yt_dlp_server.app import create_app
from yt_dlp_server.settings import Settings


@pytest.fixture
def client(monkeypatch: pytest.MonkeyPatch) -> Iterator[TestClient]:
    monkeypatch.setattr(
        "yt_dlp_server.worker.build_yt_dlp_cmd",
        lambda **kwargs: ("true",),
    )
    app = create_app(Settings(n_workers=1))
    with TestClient(app) as test_client:
        yield test_client


def _wait_for_status(
    client: TestClient,
    job_id: str,
    statuses: set[str],
    *,
    timeout: float = 5,
) -> dict[str, Any]:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        detail = client.post("/api/getJob", json={"id": job_id})
        body = detail.json()
        if body["status"] in statuses:
            return body
        time.sleep(0.05)
    raise AssertionError(f"job {job_id} did not reach {statuses}")


def test_create_job_rejects_invalid_url(client: TestClient) -> None:
    # Act
    response = client.post("/api/createJob", json={"url": "not-a-url"})

    # Assert
    assert response.status_code == 422


def test_index_shows_package_version(client: TestClient) -> None:
    # Arrange
    from yt_dlp_server.version import get_version

    # Act
    response = client.get("/")

    # Assert
    assert response.status_code == 200
    assert f">{get_version()}</span>" in response.text
    assert "__VERSION__" not in response.text


def test_create_job_returns_201(client: TestClient) -> None:
    # Act
    response = client.post(
        "/api/createJob",
        json={"url": "https://example.com/video"},
    )

    # Assert
    assert response.status_code == 201
    body = response.json()
    assert body["url"] == "https://example.com/video"
    assert "id" in body


def test_created_job_appears_in_list(client: TestClient) -> None:
    # Arrange
    created = client.post(
        "/api/createJob",
        json={"url": "https://example.com/video"},
    )
    job_id = created.json()["id"]

    # Act
    listed = client.post("/api/listJobs", json={})

    # Assert
    assert listed.status_code == 200
    ids = [job["id"] for job in listed.json()]
    assert job_id in ids


def test_get_job_returns_detail(client: TestClient) -> None:
    # Arrange
    created = client.post(
        "/api/createJob",
        json={"url": "https://example.com/video"},
    )
    job_id = created.json()["id"]

    # Act
    detail = client.post("/api/getJob", json={"id": job_id})

    # Assert
    assert detail.status_code == 200
    assert detail.json()["url"] == "https://example.com/video"


def test_get_job_returns_404_for_unknown_id(client: TestClient) -> None:
    # Act
    response = client.post("/api/getJob", json={"id": "does-not-exist"})

    # Assert
    assert response.status_code == 404


def test_cancel_job_marks_queued_as_cancelled(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Arrange: occupy the only worker so the second job stays queued
    monkeypatch.setattr(
        "yt_dlp_server.worker.build_yt_dlp_cmd",
        lambda **kwargs: ("sleep", "60"),
    )
    app = create_app(Settings(n_workers=1))
    with TestClient(app) as client:
        running = client.post(
            "/api/createJob",
            json={"url": "https://example.com/running"},
        )
        _wait_for_status(client, running.json()["id"], {"running"})
        created = client.post(
            "/api/createJob",
            json={"url": "https://example.com/queued"},
        )
        job_id = created.json()["id"]
        assert (
            client.post("/api/getJob", json={"id": job_id}).json()["status"] == "queued"
        )

        # Act
        response = client.post("/api/cancelJob", json={"id": job_id})

        # Assert
        assert response.status_code == 200
        body = response.json()
        assert body["id"] == job_id
        assert body["status"] == "cancelled"


def test_cancel_job_cancels_running(monkeypatch: pytest.MonkeyPatch) -> None:
    # Arrange
    monkeypatch.setattr(
        "yt_dlp_server.worker.build_yt_dlp_cmd",
        lambda **kwargs: ("sleep", "60"),
    )
    app = create_app(Settings(n_workers=1))
    with TestClient(app) as client:
        created = client.post(
            "/api/createJob",
            json={"url": "https://example.com/video"},
        )
        job_id = created.json()["id"]
        _wait_for_status(client, job_id, {"running"})

        # Act
        response = client.post("/api/cancelJob", json={"id": job_id})

        # Assert
        assert response.status_code == 200
        assert response.json()["status"] == "cancelled"


def test_cancel_job_returns_404_for_unknown_id(client: TestClient) -> None:
    # Act
    response = client.post("/api/cancelJob", json={"id": "does-not-exist"})

    # Assert
    assert response.status_code == 404


def test_cancel_job_returns_409_when_already_finished(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Arrange
    monkeypatch.setattr(
        "yt_dlp_server.worker.build_yt_dlp_cmd",
        lambda **kwargs: ("true",),
    )
    app = create_app(Settings(n_workers=1))
    with TestClient(app) as client:
        created = client.post(
            "/api/createJob",
            json={"url": "https://example.com/video"},
        )
        job_id = created.json()["id"]
        _wait_for_status(client, job_id, {"succeeded", "failed", "cancelled"})

        # Act
        response = client.post("/api/cancelJob", json={"id": job_id})

        # Assert
        assert response.status_code == 409


def test_create_job_returns_503_when_at_capacity(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Arrange
    monkeypatch.setattr(
        "yt_dlp_server.worker.build_yt_dlp_cmd",
        lambda **kwargs: ("sleep", "60"),
    )
    app = create_app(Settings(n_workers=1, max_jobs=1))
    with TestClient(app) as client:
        first = client.post(
            "/api/createJob",
            json={"url": "https://example.com/1"},
        )
        assert first.status_code == 201

        # Act
        second = client.post(
            "/api/createJob",
            json={"url": "https://example.com/2"},
        )

        # Assert
        assert second.status_code == 503
