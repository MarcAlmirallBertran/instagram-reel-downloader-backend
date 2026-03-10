import pytest
from app.services import download


@pytest.fixture()
def post_mock(mocker):
    mock_post = mocker.MagicMock()
    mock_post.shortcode = "shortcode"
    return mock_post
    

@pytest.fixture()
def get_post_mock_ok(mocker, post_mock):
    mocker.patch(
        "app.services.download.instaloader.structures.Post.from_shortcode",
        return_value=post_mock,
    )
    

@pytest.fixture()
def get_post_mock_not_found(mocker):
    mocker.patch(
        "app.services.download.instaloader.structures.Post.from_shortcode",
        side_effect=Exception("Post not found"),
    )
    

@pytest.fixture()
def download_post_mock_ok(mocker):
    mocker.patch(
        "app.services.download.L.download_post",
        return_value=True,
    )


@pytest.fixture()
def download_post_mock_connection_error(mocker):
    mocker.patch(
        "app.services.download.L.download_post",
        side_effect=Exception("Connection error"),
    )
    

@pytest.fixture()
def download_post_mock_failed(mocker):
    mocker.patch(
        "app.services.download.L.download_post",
        return_value=False,
    )


@pytest.mark.anyio
async def test_download_reel_ok(get_post_mock_ok, download_post_mock_ok):
    assert await download.download_reel("shortcode") == "Instagram reel downloaded successfully."


@pytest.mark.anyio
async def test_download_reel_post_not_found(get_post_mock_not_found):
    assert await download.download_reel("shortcode") == "Instagram post not found."    


@pytest.mark.anyio
async def test_download_reel_connection_error(get_post_mock_ok, download_post_mock_connection_error):
    assert await download.download_reel("shortcode") == "Connection error with Instagram."


@pytest.mark.anyio
async def test_download_reel_failed(get_post_mock_ok, download_post_mock_failed):
    assert await download.download_reel("shortcode") == "Failed to download the Instagram reel."
