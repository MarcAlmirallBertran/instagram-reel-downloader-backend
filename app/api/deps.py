import os
import typing
import uuid

import fastapi
import fastapi.security
import jwt
import sqlmodel
from collections.abc import Generator

from starlette import status
from app.core.db import engine


oauth2_scheme = fastapi.security.OAuth2PasswordBearer(tokenUrl="users/login")


def get_db() -> Generator[sqlmodel.Session, None, None]:
    with sqlmodel.Session(engine) as session:
        yield session


def get_current_user(
    token: typing.Annotated[str, fastapi.Depends(oauth2_scheme)],
    session: sqlmodel.Session = fastapi.Depends(get_db),
):
    from app.models import User

    secret = os.environ.get("JWT_SECRET_KEY", "dev-secret-change-in-production")
    try:
        payload = jwt.decode(token, secret, algorithms=["HS256"])
    except jwt.InvalidTokenError:
        raise fastapi.HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid or expired token.")

    user_id = payload.get("sub")
    if not user_id:
        raise fastapi.HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token.")

    user = session.get(User, uuid.UUID(user_id))
    if not user:
        raise fastapi.HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="User not found.")

    return user


SessionDep = typing.Annotated[sqlmodel.Session, fastapi.Depends(get_db)]
CurrentUserDep = typing.Annotated[typing.Any, fastapi.Depends(get_current_user)]
