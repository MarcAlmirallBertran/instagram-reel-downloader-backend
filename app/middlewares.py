import uuid

import sqlmodel
from sqlmodel import select
from taskiq import TaskiqMiddleware, TaskiqMessage, TaskiqResult

from app.core.db import engine
from app.models import Task, TaskError, TaskStatus, TaskStep


class ErrorHandlerMiddleware(TaskiqMiddleware):
    async def on_error(
        self,
        message: TaskiqMessage,
        result: TaskiqResult,
        exception: BaseException,
    ) -> None:
        task_id = message.args[1] if len(message.args) > 1 else None
        step: str | None = message.labels.get("step")

        if not task_id or not step:
            return

        with sqlmodel.Session(engine) as session:
            step_record = session.exec(select(TaskStep).where(TaskStep.code == step)).one_or_none()
            if not step_record:
                return

            session.add(TaskError(
                task_id=uuid.UUID(task_id),
                step_code=step_record.id,
                message=str(exception),
            ))

            failed_status = session.exec(select(TaskStatus).where(TaskStatus.code == "failed")).one()
            task = session.get(Task, uuid.UUID(task_id))
            if task:
                task.status_code = failed_status.id

            session.commit()
