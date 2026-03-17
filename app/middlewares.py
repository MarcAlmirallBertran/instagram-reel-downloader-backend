import logging
import uuid

import sqlmodel
from sqlmodel import select
from taskiq import TaskiqMiddleware, TaskiqMessage, TaskiqResult

from app.core.db import engine
from app.exceptions import TaskCancelledException
from app.models import Task, TaskError, TaskStatus, TaskStep


logger = logging.getLogger(__name__)


class ErrorHandlerMiddleware(TaskiqMiddleware):
    async def pre_send(self, message: TaskiqMessage) -> TaskiqMessage:
        task_id = message.kwargs.get("task_id")
        if not task_id:
            return message

        with sqlmodel.Session(engine) as session:
            task = session.get(Task, uuid.UUID(task_id))
            if task and task.cancelled:
                logger.info(f"Task {task_id} is cancelled.")
                raise TaskCancelledException(f"Task {task_id} was cancelled.")

        return message

    async def post_execute(
        self,
        message: TaskiqMessage,
        result: TaskiqResult,
    ) -> None:
        task_id = message.kwargs.get("task_id")
        if not task_id:
            return

        with sqlmodel.Session(engine) as session:
            task = session.get(Task, uuid.UUID(task_id))
            if not task or not task.cancelled:
                return

            cancelled_status = session.exec(
                select(TaskStatus).where(TaskStatus.code == "cancelled")
            ).one()
            task.status_code = cancelled_status.id
            logger.info(f"Task {task_id} marked as cancelled after execution.")
            session.commit()

    async def on_error(
        self,
        message: TaskiqMessage,
        result: TaskiqResult,
        exception: BaseException,
    ) -> None:
        if isinstance(exception, TaskCancelledException):
            return

        task_id: str | None = message.kwargs.get("task_id")
        step: str | None = message.labels.get("step")

        if not task_id or not step:
            return
            
        logger.error(f"Error in task {task_id} at step {step}: {exception}")
        with sqlmodel.Session(engine) as session:
            step_record = session.exec(select(TaskStep).where(TaskStep.code == step)).one()
            task = session.exec(select(Task).where(Task.id == uuid.UUID(task_id))).one()
            
            task_error = TaskError(
                task_id=task.id,
                step_code=step_record.id,
                message=str(exception),
                detail=getattr(exception, "detail", None),
            )
            session.add(task_error)

            failed_status = session.exec(select(TaskStatus).where(TaskStatus.code == "failed")).one()
            task.status_code = failed_status.id

            session.commit()
