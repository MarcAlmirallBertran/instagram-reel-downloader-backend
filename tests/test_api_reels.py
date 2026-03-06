from unittest.mock import AsyncMock, patch

import pytest
from httpx import ASGITransport, AsyncClient

from app.application.services.reel_service import ReelService
from app.core.dependencies import get_reel_service
from app.domain.models.reel import DownloadStatus, ReelDownloadResult
from app.main import app


@pytest.fixture
def mock_reel_service() -> ReelService:
    return AsyncMock(spec=ReelService)


@pytest.fixture
async def client(mock_reel_service: ReelService) -> AsyncClient:
    app.dependency_overrides[get_reel_service] = lambda: mock_reel_service
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        yield c
    app.dependency_overrides.clear()


async def test_health_check(client: AsyncClient) -> None:
    response = await client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


async def test_download_reel_success(
    client: AsyncClient, mock_reel_service: AsyncMock
) -> None:
    mock_reel_service.request_download.return_value = ReelDownloadResult(
        reel_url="https://www.instagram.com/reel/CxABCDEFGH/",
        status=DownloadStatus.COMPLETED,
        download_url="https://cdn.example.com/video.mp4",
    )

    response = await client.post(
        "/api/v1/reels/download",
        json={"reel_url": "https://www.instagram.com/reel/CxABCDEFGH/"},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "completed"
    assert body["download_url"] == "https://cdn.example.com/video.mp4"


async def test_download_reel_failure_returns_422(
    client: AsyncClient, mock_reel_service: AsyncMock
) -> None:
    mock_reel_service.request_download.return_value = ReelDownloadResult(
        reel_url="https://www.instagram.com/reel/CxABCDEFGH/",
        status=DownloadStatus.FAILED,
        error="Invalid Instagram Reel URL",
    )

    response = await client.post(
        "/api/v1/reels/download",
        json={"reel_url": "https://www.instagram.com/reel/CxABCDEFGH/"},
    )

    assert response.status_code == 422
    assert "Invalid Instagram Reel URL" in response.json()["detail"]


async def test_download_reel_invalid_url_returns_422(client: AsyncClient) -> None:
    response = await client.post(
        "/api/v1/reels/download",
        json={"reel_url": "not-a-url"},
    )
    assert response.status_code == 422
