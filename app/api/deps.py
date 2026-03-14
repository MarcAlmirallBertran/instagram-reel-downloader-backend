import typing
import fastapi
import sqlmodel
from collections.abc import Generator
from app.core.db import engine


def get_db() -> Generator[sqlmodel.Session, None, None]:
    with sqlmodel.Session(engine) as session:
        yield session
        
SessionDep = typing.Annotated[sqlmodel.Session, fastapi.Depends(get_db)]