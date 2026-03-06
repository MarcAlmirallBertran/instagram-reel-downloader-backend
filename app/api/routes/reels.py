from fastapi import APIRouter, Depends, HTTPException, status

from app.application.services.reel_service import ReelService
from app.core.dependencies import get_reel_service
from app.domain.models.reel import DownloadStatus, ReelDownloadRequest, ReelDownloadResult

router = APIRouter(prefix="/reels", tags=["reels"])


@router.post(
    "/download",
    response_model=ReelDownloadResult,
    status_code=status.HTTP_200_OK,
    summary="Request a reel download",
    description=(
        "Accepts an Instagram Reel URL, publishes a download-requested event, "
        "and returns the resolved direct video URL when available."
    ),
)
async def download_reel(
    request: ReelDownloadRequest,
    reel_service: ReelService = Depends(get_reel_service),
) -> ReelDownloadResult:
    result = await reel_service.request_download(str(request.reel_url))
    if result.status == DownloadStatus.FAILED:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=result.error,
        )
    return result
