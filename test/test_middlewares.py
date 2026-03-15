import uuid

import pytest
import sqlmodel
from sqlmodel import select
from taskiq import TaskiqMessage, TaskiqResult

from app.exceptions import TaskCancelledException
from app.middlewares import ErrorHandlerMiddleware
from app.models import Task, TaskError, TaskStatus


@pytest.fixture()
def task_in_db(db_session: sqlmodel.Session) -> Task:
    pending_status = db_session.exec(select(TaskStatus).where(TaskStatus.code == "pending")).one()
    task = Task(url="https://www.instagram.com/reel/middleware_shortcode/", status_code=pending_status.id)
    db_session.add(task)
    db_session.commit()
    db_session.refresh(task)
    return task


@pytest.fixture()
def cancelled_task_in_db(db_session: sqlmodel.Session) -> Task:
    cancelled_status = db_session.exec(select(TaskStatus).where(TaskStatus.code == "cancelled")).one()
    task = Task(
        url="https://www.instagram.com/reel/middleware_cancelled_shortcode/",
        status_code=cancelled_status.id,
        cancelled=True,
    )
    db_session.add(task)
    db_session.commit()
    db_session.refresh(task)
    return task


def _make_message(task_id: str, step: str = "download") -> TaskiqMessage:
    return TaskiqMessage(
        task_id="test-task-id",
        task_name="app.services.download:download_reel",
        labels={"step": step},
        args=[],
        kwargs={"short_code": "shortcode", "task_id": task_id},
    )


# --- pre_send ---

@pytest.mark.anyio
async def test_pre_send_cancelled_task_raises(cancelled_task_in_db):
    message = _make_message(str(cancelled_task_in_db.id))
    middleware = ErrorHandlerMiddleware()
    with pytest.raises(TaskCancelledException):
        await middleware.pre_send(message)


@pytest.mark.anyio
async def test_pre_send_pending_task_passes(task_in_db):
    message = _make_message(str(task_in_db.id))
    middleware = ErrorHandlerMiddleware()
    result = await middleware.pre_send(message)
    assert result is message


@pytest.mark.anyio
async def test_pre_send_missing_task_id():
    message = TaskiqMessage(
        task_id="test-task-id",
        task_name="app.services.download:download_reel",
        labels={"step": "download"},
        args=[],
        kwargs={},
    )
    middleware = ErrorHandlerMiddleware()
    result = await middleware.pre_send(message)
    assert result is message


# --- post_execute ---

@pytest.mark.anyio
async def test_post_execute_overrides_completed_if_cancelled(cancelled_task_in_db, db_session):
    # Simulate: step finished and set status to completed before cancellation was checked
    completed_status = db_session.exec(select(TaskStatus).where(TaskStatus.code == "completed")).one()
    cancelled_task_in_db.status_code = completed_status.id
    db_session.commit()

    message = _make_message(str(cancelled_task_in_db.id))
    result = TaskiqResult(is_err=False, return_value="ok", execution_time=0.1, labels={})
    middleware = ErrorHandlerMiddleware()
    await middleware.post_execute(message, result)

    db_session.refresh(cancelled_task_in_db)
    cancelled_status = db_session.exec(select(TaskStatus).where(TaskStatus.code == "cancelled")).one()
    assert cancelled_task_in_db.status_code == cancelled_status.id


@pytest.mark.anyio
async def test_post_execute_no_op_if_not_cancelled(task_in_db, db_session):
    completed_status = db_session.exec(select(TaskStatus).where(TaskStatus.code == "completed")).one()
    task_in_db.status_code = completed_status.id
    db_session.commit()

    message = _make_message(str(task_in_db.id))
    result = TaskiqResult(is_err=False, return_value="ok", execution_time=0.1, labels={})
    middleware = ErrorHandlerMiddleware()
    await middleware.post_execute(message, result)

    db_session.refresh(task_in_db)
    assert task_in_db.status_code == completed_status.id


# --- on_error ---

@pytest.mark.anyio
async def test_on_error_skips_cancelled_exception(cancelled_task_in_db, db_session):
    message = _make_message(str(cancelled_task_in_db.id))
    result = TaskiqResult(is_err=True, return_value=None, execution_time=0.1, labels={})
    middleware = ErrorHandlerMiddleware()
    await middleware.on_error(message, result, TaskCancelledException("cancelled"))

    db_session.expire_all()

    task_errors = db_session.exec(
        select(TaskError).where(TaskError.task_id == cancelled_task_in_db.id)
    ).all()
    assert len(task_errors) == 0

    db_session.refresh(cancelled_task_in_db)
    cancelled_status = db_session.exec(select(TaskStatus).where(TaskStatus.code == "cancelled")).one()
    assert cancelled_task_in_db.status_code == cancelled_status.id


@pytest.mark.anyio
async def test_on_error_handles_regular_exception(task_in_db, db_session):
    message = _make_message(str(task_in_db.id), step="download")
    result = TaskiqResult(is_err=True, return_value=None, execution_time=0.1, labels={})
    middleware = ErrorHandlerMiddleware()
    await middleware.on_error(message, result, RuntimeError("something went wrong"))

    db_session.expire_all()

    task_error = db_session.exec(
        select(TaskError).where(TaskError.task_id == task_in_db.id)
    ).one()
    assert task_error.message == "something went wrong"

    db_session.refresh(task_in_db)
    failed_status = db_session.exec(select(TaskStatus).where(TaskStatus.code == "failed")).one()
    assert task_in_db.status_code == failed_status.id
