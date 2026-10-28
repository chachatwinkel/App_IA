import sqlite3

import pytest
from werkzeug.security import check_password_hash

from app import create_app


@pytest.fixture
def app(tmp_path):
    database_path = tmp_path / "incidencias-test.db"
    application = create_app(
        {
            "TESTING": True,
            "DATABASE": str(database_path),
            "SECRET_KEY": "test-secret",
            "DEMO_USER_PASSWORD": "user-test-password",
            "DEMO_TECHNICIAN_PASSWORD": "technician-test-password",
        }
    )
    yield application


@pytest.fixture
def client(app):
    return app.test_client()


def login(client, username, password):
    client.get("/login")
    with client.session_transaction() as session:
        token = session["_csrf_token"]
    return client.post(
        "/login",
        data={
            "username": username,
            "password": password,
            "csrf_token": token,
        },
        follow_redirects=True,
    )


def test_seeded_passwords_are_stored_as_hashes(app):
    with sqlite3.connect(app.config["DATABASE"]) as connection:
        users = connection.execute(
            "SELECT username, password_hash, role FROM users ORDER BY username"
        ).fetchall()

    assert [(user[0], user[2]) for user in users] == [
        ("tecnico", "tecnico"),
        ("usuario", "usuario"),
    ]
    assert check_password_hash(users[0][1], "technician-test-password")
    assert check_password_hash(users[1][1], "user-test-password")


def test_user_can_login_and_see_user_panel(client):
    response = login(client, "usuario", "user-test-password")

    assert response.status_code == 200
    assert "Usuario" in response.get_data(as_text=True)


def test_technician_can_login_and_see_technician_panel(client):
    response = login(client, "tecnico", "technician-test-password")

    assert response.status_code == 200
    assert "Técnico" in response.get_data(as_text=True)


def test_user_cannot_open_technician_panel(client):
    login(client, "usuario", "user-test-password")

    assert client.get("/tecnico").status_code == 403


def test_technician_cannot_open_user_panel(client):
    login(client, "tecnico", "technician-test-password")

    assert client.get("/usuario").status_code == 403


def test_invalid_password_does_not_log_in(client):
    response = login(client, "usuario", "wrong-password")

    assert response.status_code == 200
    assert "Usuario o contraseña incorrectos." in response.get_data(as_text=True)
    assert client.get("/usuario").status_code == 302


def test_login_rejects_missing_csrf_token(client):
    response = client.post(
        "/login",
        data={"username": "usuario", "password": "user-test-password"},
    )

    assert response.status_code == 400
