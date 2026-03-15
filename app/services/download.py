import logging
import pathlib
import tempfile
import uuid

import instaloader
import sqlmodel
from taskiq import TaskiqDepends

from app.broker import broker
from app.api.deps import get_db
from app.models import Download, Task, TaskStatus
from app.services.audio import extract_audio

media_dir = pathlib.Path(tempfile.gettempdir()) / "reels"
media_dir.mkdir(exist_ok=True)
logger = logging.getLogger(__name__)
L = instaloader.Instaloader(
    save_metadata=False,
    filename_pattern="{shortcode}",
    post_metadata_txt_pattern="",
)


@broker.task(step="download")
async def download_reel(
    short_code: str,
    task_id: str,
    session: sqlmodel.Session = TaskiqDepends(get_db),
):
    logger.info(f"Starting download for task {task_id} with shortcode {short_code}")
    in_progress_status = session.exec(sqlmodel.select(TaskStatus).where(TaskStatus.code == "in_progress")).one()

    task = session.get(Task, uuid.UUID(task_id))
    if task and task.cancelled:
        return "Task was cancelled."
    if task:
        task.status_code = in_progress_status.id
        session.commit()

    post = instaloader.structures.Post.from_shortcode(L.context, short_code)

    target = media_dir.joinpath(task_id)
    download_response = L.download_post(post, target=target)

    if not download_response:
        raise RuntimeError(f"Failed to download the Instagram reel for shortcode {short_code}.")

    db_download = Download(
        shortcode=post.shortcode,
        file_path=str(target),
    )
    session.add(db_download)

    if task:
        task.download_id = db_download.id

    session.commit()

    await extract_audio.kiq(download_id=str(db_download.id), task_id=task_id)

    return "Instagram reel downloaded successfully."
