import logging
import mimetypes
import os
import pathlib
import tempfile
import uuid

import instaloader
import sqlmodel
from taskiq import TaskiqDepends

from app.api.deps import get_db
from app.broker import broker
from app.core.encryption import decrypt
from app.models import File, Task, TaskStatus, User
from app.services.audio import extract_audio

media_dir = pathlib.Path(
    os.environ.get("MEDIA_DIR", pathlib.Path(tempfile.gettempdir()) / "reels")
)
media_dir.mkdir(exist_ok=True)
logger = logging.getLogger(__name__)


def _get_instaloader(session: sqlmodel.Session, task: Task) -> instaloader.Instaloader:
    loader = instaloader.Instaloader(
        save_metadata=False,
        filename_pattern="{shortcode}",
        post_metadata_txt_pattern="",
    )
    user = session.get(User, task.user_id)
    if user and user.instagram_username and user.instagram_password:
        loader.login(decrypt(user.instagram_username), decrypt(user.instagram_password))
        return loader
    return loader


@broker.task(step="download")
async def download_reel(
    task_id: str,
    session: sqlmodel.Session = TaskiqDepends(get_db),
):
    logger.info(f"Starting download video for task {task_id}")

    task = session.exec(
        sqlmodel.select(Task).where(Task.id == uuid.UUID(task_id))
    ).one()
    
    if task.cancelled:
        return "Task was cancelled."
        
    in_progress_status = session.exec(
        sqlmodel.select(TaskStatus).where(TaskStatus.code == "in_progress")
    ).one()

    task.status_code = in_progress_status.id
    session.commit()

    loader = _get_instaloader(session, task)

    post = instaloader.structures.Post.from_shortcode(loader.context, task.short_code)

    target = media_dir.joinpath(task_id)
    download_response = loader.download_post(post, target=target)

    if not download_response:
        raise RuntimeError(
            f"Failed to download the Instagram reel for shortcode {task.short_code}."
        )

    for file_path in target.iterdir():
        if not file_path.is_file():
            continue

        mime_type, _ = mimetypes.guess_type(file_path.name)
        if mime_type is None:
            logger.debug(f"Skipping file with unknown MIME type: {file_path}")
            continue

        db_file = File(path=str(file_path), mime_type=mime_type)
        session.add(db_file)

        if mime_type.startswith("video/"):
            task.video_id = db_file.id
        elif mime_type.startswith("image/"):
            task.thumbnail_id = db_file.id

    session.commit()

    await extract_audio.kiq(task_id=task_id)

    return "Instagram reel downloaded successfully."
