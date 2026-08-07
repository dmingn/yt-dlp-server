from collections.abc import Iterator

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
