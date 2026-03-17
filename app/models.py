import uuid
from datetime import datetime

import sqlmodel


class File(sqlmodel.SQLModel, table=True):
    id:         uuid.UUID = sqlmodel.Field(default_factory=uuid.uuid4, primary_key=True)
    path:       str
    mime_type:  str
    created_at: datetime  = sqlmodel.Field(default_factory=datetime.now)


class TaskStatus(sqlmodel.SQLModel, table=True):
    id:   uuid.UUID = sqlmodel.Field(default_factory=uuid.uuid4, primary_key=True)
    code: str       = sqlmodel.Field(unique=True)


class TaskStep(sqlmodel.SQLModel, table=True):
    id:   uuid.UUID = sqlmodel.Field(default_factory=uuid.uuid4, primary_key=True)
    code: str       = sqlmodel.Field(unique=True)


class Task(sqlmodel.SQLModel, table=True):
    id:            uuid.UUID        = sqlmodel.Field(default_factory=uuid.uuid4, primary_key=True)
    short_code:    str
    status_code:   uuid.UUID        = sqlmodel.Field(foreign_key="taskstatus.id")
    user_id:       uuid.UUID        = sqlmodel.Field(foreign_key="user.id")
    thumbnail_id:  uuid.UUID | None = sqlmodel.Field(default=None, foreign_key="file.id")
    video_id:      uuid.UUID | None = sqlmodel.Field(default=None, foreign_key="file.id")
    audio_id:      uuid.UUID | None = sqlmodel.Field(default=None, foreign_key="file.id")
    transcript_id: uuid.UUID | None = sqlmodel.Field(default=None, foreign_key="file.id")
    topics:        str | None       = None
    language:      str | None       = None
    cancelled:     bool             = sqlmodel.Field(default=False)
    created_at:    datetime         = sqlmodel.Field(default_factory=datetime.now)
    updated_at:    datetime         = sqlmodel.Field(default_factory=datetime.now, sa_column_kwargs={"onupdate": datetime.now})


class User(sqlmodel.SQLModel, table=True):
    id:                 uuid.UUID = sqlmodel.Field(default_factory=uuid.uuid4, primary_key=True)
    username:           str       = sqlmodel.Field(unique=True, index=True)
    hashed_password:    str
    openai_api_key:     str | None = sqlmodel.Field(default=None)
    instagram_username: str | None = sqlmodel.Field(default=None)
    instagram_password: str | None = sqlmodel.Field(default=None)
    created_at:         datetime  = sqlmodel.Field(default_factory=datetime.now)


class TaskError(sqlmodel.SQLModel, table=True):
    id:        uuid.UUID = sqlmodel.Field(default_factory=uuid.uuid4, primary_key=True)
    task_id:   uuid.UUID = sqlmodel.Field(foreign_key="task.id")
    step_code: uuid.UUID = sqlmodel.Field(foreign_key="taskstep.id")
    message:   str
    detail:    str | None = None
    created_at: datetime = sqlmodel.Field(default_factory=datetime.now)

