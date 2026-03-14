import os

import sqlmodel
from sqlalchemy.pool import StaticPool
from app.models import TaskStatus, TaskStep

TASK_STATUSES = [
    "pending",
    "in_progress",
    "processing",
    "completed",
    "failed",
    "cancelled",
]

TASK_STEPS = [
    "download",
    "audio",
    "transcript",
]

DATABASE_URL = os.environ.get(
    "DATABASE_URL",
    "postgresql://postgres:1234@localhost:5432/postgres",
)

connect_args = {"check_same_thread": False} if DATABASE_URL.startswith("sqlite") else {}
poolclass = StaticPool if DATABASE_URL == "sqlite://" else None
engine = sqlmodel.create_engine(DATABASE_URL, connect_args=connect_args, poolclass=poolclass)


def create_tables() -> None:
    sqlmodel.SQLModel.metadata.create_all(engine)


def seed_db(session: sqlmodel.Session) -> None:
    for code in TASK_STATUSES:
        result = session.exec(sqlmodel.select(TaskStatus).where(TaskStatus.code == code)).one_or_none()
        if result is None:
            session.add(TaskStatus(code=code))

    for code in TASK_STEPS:
        result = session.exec(sqlmodel.select(TaskStep).where(TaskStep.code == code)).one_or_none()
        if result is None:
            session.add(TaskStep(code=code))

    session.commit()


def init_db() -> None:
    create_tables()
    
    with sqlmodel.Session(engine) as session:
        seed_db(session)
