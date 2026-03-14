import logging
import pathlib
import uuid

import openai
import pydantic
import sqlmodel
from taskiq import TaskiqDepends

from app.broker import broker
from app.api.deps import get_db
from app.models import AudioTrack, Task, TaskStatus, Transcript

logger = logging.getLogger(__name__)

client = openai.AsyncOpenAI(
      http_client=openai.DefaultAioHttpClient(),
)

class Topics(pydantic.BaseModel):
    topics: list[str] 


async def extract_topics_llm(transcription: str) -> str | None:
    try:
        response = await client.chat.completions.parse(
            model="gpt-4o-mini",
            messages=[
                {
                    "role": "system",
                    "content": """Eres un experto en análisis de contenido.
                Extrae los key topics de la transcripción proporcionada.
                """
                },
                {
                    "role": "user",
                    "content": f"Transcripción del reel:\n\n{transcription}"
                }
            ],
            temperature=0.3,
            response_format=Topics
        )
    except openai.APIError as e:
        logger.warning(f"Failed to call LLM for topics extraction: {e}")
        return None

    try:
        parsed = response.choices[0].message.parsed
    except (IndexError, AttributeError) as e:
        logger.warning(f"Failed to parse LLM response: {e}")
        return None
    
    if not parsed or not parsed.topics:
        return None
    
    topics = [topic.strip() for topic in parsed.topics if topic.strip()]
    
    return ", ".join(topics) if topics else None

@broker.task(step="transcript")
async def transcribe_audio(
    audio_track_id: str,
    task_id: str,
    session: sqlmodel.Session = TaskiqDepends(get_db),
):
    db_audio_track = session.get(AudioTrack, uuid.UUID(audio_track_id))
    if not db_audio_track:
        raise RuntimeError(f"AudioTrack {audio_track_id} not found.")

    try:
        with open(db_audio_track.file_path, "rb") as f:
            response = await client.audio.transcriptions.create(
                model="whisper-1",
                file=f,
                response_format="verbose_json",
            )
    except openai.APIError as e:
        if isinstance(e.body, dict):
            raise RuntimeError(e.body["message"]) from e
        raise RuntimeError(str(e)) from e

    transcript_path = pathlib.Path(db_audio_track.file_path).with_suffix(".txt")
    transcript_path.write_text(response.text, encoding="utf-8")
    
    topics = await extract_topics_llm(response.text)

    db_transcript = Transcript(
        audio_track_id=uuid.UUID(audio_track_id),
        file_path=str(transcript_path),
        language=response.language,
        topics=topics,
    )
    session.add(db_transcript)

    completed_status = session.exec(
        sqlmodel.select(TaskStatus).where(TaskStatus.code == "completed")
    ).one()

    task = session.get(Task, uuid.UUID(task_id))
    if task:
        task.status_code = completed_status.id

    session.commit()

    return "Audio transcribed successfully."
