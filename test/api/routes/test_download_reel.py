from fastapi.testclient import TestClient
from fastapi import status
import pytest


@pytest.fixture()
def post_mock(mocker):
    mock_post = mocker.MagicMock()
    mock_post.shortcode = "shortcode"
    return mock_post
    

@pytest.fixture()
def get_post_mock(mocker, post_mock):
    mocker.patch(
        "app.api.routes.download_reel.Post.from_shortcode",
        return_value=post_mock,
    )
    

@pytest.fixture()
def download_post_failed_mock(mocker):
    mocker.patch(
        "app.api.routes.download_reel.L.download_post",
        return_value=False,
    )
    

@pytest.fixture()
def download_post_mock(mocker):
    mocker.patch(
        "app.api.routes.download_reel.L.download_post",
        return_value=True,
    )


def test_download_ok(get_post_mock, download_post_mock, client: TestClient):
    data = {"uri": "https://www.instagram.com/reel/shortcode/"}
    response = client.post("/download-reel", json=data)
    assert response.status_code == status.HTTP_200_OK
    assert response.json() == {"message": "Instagram reel downloaded successfully."}


def test_download_bad_url(client: TestClient):
    data = {"uri": "https://www.test.com/reel/shortcode/"}
    response = client.post("/download-reel", json=data)
    assert response.status_code == status.HTTP_400_BAD_REQUEST
    assert response.json() == {"message": "Invalid URI. Only Instagram URLs are allowed."}


def test_download_bad_format(client: TestClient):
    data = {"uri": "https://www.instagram.com/test/"}
    response = client.post("/download-reel", json=data)
    assert response.status_code == status.HTTP_400_BAD_REQUEST
    assert response.json() == {"message": "Invalid URI. The path is not valid for an Instagram reel."}


def test_download_failed(get_post_mock, download_post_failed_mock, client: TestClient):
    data = {"uri": "https://www.instagram.com/reel/shortcode/"}
    response = client.post("/download-reel", json=data)
    assert response.status_code == status.HTTP_500_INTERNAL_SERVER_ERROR
    assert response.json() == {"message": "Failed to download the Instagram reel."}