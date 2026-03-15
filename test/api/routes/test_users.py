import bcrypt
import sqlmodel
from fastapi import status
from fastapi.testclient import TestClient
from sqlmodel import select

from app.models import User


def test_create_user_ok(client: TestClient, db_session: sqlmodel.Session):
    response = client.post("/users", json={"username": "testuser", "password": "secret123"})
    assert response.status_code == status.HTTP_201_CREATED
    data = response.json()
    assert data["username"] == "testuser"
    assert "id" in data

    user = db_session.exec(select(User).where(User.username == "testuser")).one()
    assert user.hashed_password != "secret123"
    assert bcrypt.checkpw(b"secret123", user.hashed_password.encode())


def test_create_user_duplicate_username(client: TestClient):
    client.post("/users", json={"username": "dupeuser", "password": "pass1"})
    response = client.post("/users", json={"username": "dupeuser", "password": "pass2"})
    assert response.status_code == status.HTTP_409_CONFLICT
    assert response.json() == {"message": "Username already exists."}


def test_create_user_missing_fields(client: TestClient):
    response = client.post("/users", json={"username": "onlyuser"})
    assert response.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY


def test_login_ok(client: TestClient):
    client.post("/users", json={"username": "loginuser", "password": "mypassword"})
    response = client.post("/users/login", data={"username": "loginuser", "password": "mypassword"})
    assert response.status_code == status.HTTP_200_OK
    data = response.json()
    assert "access_token" in data
    assert data["token_type"] == "bearer"


def test_login_wrong_password(client: TestClient):
    client.post("/users", json={"username": "wrongpassuser", "password": "correct"})
    response = client.post("/users/login", data={"username": "wrongpassuser", "password": "wrong"})
    assert response.status_code == status.HTTP_401_UNAUTHORIZED


def test_login_user_not_found(client: TestClient):
    response = client.post("/users/login", data={"username": "nonexistent_xyz", "password": "pass"})
    assert response.status_code == status.HTTP_401_UNAUTHORIZED


def test_protected_endpoint_without_token(client: TestClient):
    response = client.get("/tasks")
    assert response.status_code == status.HTTP_401_UNAUTHORIZED
