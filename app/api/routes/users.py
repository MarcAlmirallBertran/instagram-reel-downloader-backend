import os
from datetime import datetime, timedelta
from typing import Annotated

import bcrypt
import jwt
from fastapi import APIRouter, Depends, status
from fastapi.responses import JSONResponse
from fastapi.security import OAuth2PasswordRequestForm
from pydantic import BaseModel
from sqlmodel import select

from app.api.deps import CurrentUserDep, SessionDep
from app.core.encryption import encrypt
from app.models import User

router = APIRouter(prefix="/users", tags=["users"])

_TOKEN_EXPIRY_HOURS = 24


def _jwt_secret() -> str:
    return os.environ.get("JWT_SECRET_KEY", "dev-secret-change-in-production")


class UserCreateRequest(BaseModel):
    username: str
    password: str


class UserResponse(BaseModel):
    id: str
    username: str


class Message(BaseModel):
    message: str


class UserUpdateRequest(BaseModel):
    openai_api_key: str | None = None
    instagram_username: str | None = None
    instagram_password: str | None = None


class UserProfileResponse(BaseModel):
    id: str
    username: str
    has_openai_api_key: bool
    has_instagram_credentials: bool


@router.post(
    "",
    status_code=status.HTTP_201_CREATED,
    response_model=UserResponse,
    responses={409: {"description": "Username already exists."}},
)
async def create_user(request: UserCreateRequest, session: SessionDep):
    existing = session.exec(select(User).where(User.username == request.username)).first()
    if existing:
        return JSONResponse(
            status_code=status.HTTP_409_CONFLICT,
            content={"message": "Username already exists."},
        )

    hashed = bcrypt.hashpw(request.password.encode(), bcrypt.gensalt()).decode()
    user = User(username=request.username, hashed_password=hashed)
    session.add(user)
    session.commit()
    session.refresh(user)

    return UserResponse(id=str(user.id), username=user.username)


@router.post(
    "/login",
    status_code=status.HTTP_200_OK,
    responses={401: {"description": "Invalid credentials."}},
)
async def login(
    form_data: Annotated[OAuth2PasswordRequestForm, Depends()],
    session: SessionDep,
):
    user = session.exec(select(User).where(User.username == form_data.username)).first()
    if not user or not bcrypt.checkpw(form_data.password.encode(), user.hashed_password.encode()):
        return JSONResponse(
            status_code=status.HTTP_401_UNAUTHORIZED,
            content={"message": "Invalid username or password."},
        )

    token = jwt.encode(
        {"sub": str(user.id), "exp": datetime.now() + timedelta(hours=_TOKEN_EXPIRY_HOURS)},
        _jwt_secret(),
        algorithm="HS256",
    )
    return {"access_token": token, "token_type": "bearer"}


@router.get("/me", status_code=status.HTTP_200_OK, response_model=UserProfileResponse)
async def get_profile(current_user: CurrentUserDep):
    return UserProfileResponse(
        id=str(current_user.id),
        username=current_user.username,
        has_openai_api_key=current_user.openai_api_key is not None,
        has_instagram_credentials=(
            current_user.instagram_username is not None
            and current_user.instagram_password is not None
        ),
    )


@router.patch("/me", status_code=status.HTTP_200_OK, response_model=UserProfileResponse)
async def update_profile(
    request: UserUpdateRequest,
    session: SessionDep,
    current_user: CurrentUserDep,
):
    if request.openai_api_key is not None:
        current_user.openai_api_key = encrypt(request.openai_api_key) if request.openai_api_key else None
    if request.instagram_username is not None:
        current_user.instagram_username = encrypt(request.instagram_username) if request.instagram_username else None
    if request.instagram_password is not None:
        current_user.instagram_password = encrypt(request.instagram_password) if request.instagram_password else None

    session.add(current_user)
    session.commit()
    session.refresh(current_user)

    return UserProfileResponse(
        id=str(current_user.id),
        username=current_user.username,
        has_openai_api_key=current_user.openai_api_key is not None,
        has_instagram_credentials=(
            current_user.instagram_username is not None
            and current_user.instagram_password is not None
        ),
    )
