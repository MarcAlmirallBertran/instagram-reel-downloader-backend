import logging
from urllib.parse import urlparse

import instaloader
from fastapi import APIRouter, Response, status
from instaloader.structures import Post
from pydantic.main import BaseModel

logger = logging.getLogger(__name__)


VALID_PATH_PREFIXES = ("p", "reel", "reels", "tv")


router = APIRouter()
L = instaloader.Instaloader()


class DownloadRequest(BaseModel):
    uri: str
    
class ResponseModel(BaseModel):
    message: str


@router.post(
    "/download-reel",
    status_code=status.HTTP_200_OK,
    responses={
        200: {
            "model": ResponseModel,
            "description": "Instagram reel downloaded successfully."
        },
        400: {
            "model": ResponseModel,
            "description": "Invalid URI. The URL is not a valid Instagram post or reel."
        },
        404: {
            "model": ResponseModel,
            "description": "Instagram post not found."
        },
        500: {
            "model": ResponseModel,
            "description": "Failed to download the Instagram reel."
        },
        503: {
            "model": ResponseModel,
            "description": "Connection error with Instagram."
        },
    },
)
async def download_reel(reel_uri: DownloadRequest, response: Response):
    parsed_uri = urlparse(reel_uri.uri)

    if parsed_uri.hostname not in ("www.instagram.com", "instagram.com"):
        response.status_code = status.HTTP_400_BAD_REQUEST
        return {"message": "Invalid URI. Only Instagram URLs are allowed."}

    segments = parsed_uri.path.split("/")

    if len(segments) < 3 or segments[1] not in VALID_PATH_PREFIXES:
        response.status_code = status.HTTP_400_BAD_REQUEST
        return {"message": "Invalid URI. The path is not valid for an Instagram reel."}

    short_code = segments[2]
    try:
        post = Post.from_shortcode(L.context, short_code)
    except Exception as e:
        logger.error(f"Failed to retrieve post for shortcode {short_code}: {e}")
        response.status_code = status.HTTP_404_NOT_FOUND
        return {"message": "Instagram post not found."}

    try:
        download_response = L.download_post(post, target=post.shortcode)
    except Exception as e:
        logger.error(f"Connection error while downloading post {short_code}: {e}")
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
        return {"message": "Connection error with Instagram."}

    if not download_response:
        response.status_code = status.HTTP_500_INTERNAL_SERVER_ERROR
        return {"message": "Failed to download the Instagram reel."}

    return {"message": "Instagram reel downloaded successfully."}
