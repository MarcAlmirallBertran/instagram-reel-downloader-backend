import logging
import pathlib
import tempfile
import instaloader
from app.broker import broker

media_dir = pathlib.Path(tempfile.gettempdir()) / "reels"
media_dir.mkdir(exist_ok=True)
logger = logging.getLogger(__name__)
L = instaloader.Instaloader(
    save_metadata=False,
    filename_pattern="{shortcode}",
    post_metadata_txt_pattern = "",
)


@broker.task
async def download_reel(short_code: str):
    try:
        post = instaloader.structures.Post.from_shortcode(L.context, short_code)
    except Exception as e:
        logger.error(f"Failed to retrieve post for shortcode {short_code}: {e}")
        return "Instagram post not found."

    try:
        download_response = L.download_post(post, target=media_dir / post.shortcode)
    except Exception as e:
        logger.error(f"Connection error while downloading post {short_code}: {e}")
        return "Connection error with Instagram."

    if not download_response:
        logger.error(f"Failed to download post {short_code}.")
        return "Failed to download the Instagram reel."

    return "Instagram reel downloaded successfully."
