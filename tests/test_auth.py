import sqlite3

import pytest
from werkzeug.security import check_password_hash, generate_password_hash

import app as app_module
from app import create_app
from clasificador import CLASIFICACION_REVISAR, Clasificacion


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


def test_user_can_register_and_see_incident(client, monkeypatch):
    monkeypatch.setattr(
        app_module,
        "clasificar",
        lambda _observation: CLASIFICACION_REVISAR,
    )
    login(client, "usuario", "user-test-password")
    with client.session_transaction() as session:
        token = session["_csrf_token"]

    response = client.post(
        "/usuario",
        data={
            "observation": "No arranca el portátil",
            "csrf_token": token,
        },
        follow_redirects=True,
    )

    page = response.get_data(as_text=True)
    assert response.status_code == 200
    assert "No arranca el portátil" in page
    assert "revisar" in page
    assert "abierta" in page


def test_registration_saves_ai_classification(client, app, monkeypatch):
    monkeypatch.setattr(
        app_module,
        "clasificar",
        lambda observation: (
            Clasificacion("hardware", "alta", "El portátil no enciende")
            if observation == "No arranca el portátil"
            else CLASIFICACION_REVISAR
        ),
    )
    login(client, "usuario", "user-test-password")
    with client.session_transaction() as session:
        token = session["_csrf_token"]

    response = client.post(
        "/usuario",
        data={
            "observation": "No arranca el portátil",
            "csrf_token": token,
        },
        follow_redirects=True,
    )
    with sqlite3.connect(app.config["DATABASE"]) as connection:
        incident = connection.execute(
            "SELECT category, priority, summary FROM incidents"
        ).fetchone()

    assert response.status_code == 200
    assert incident == ("hardware", "alta", "El portátil no enciende")


def test_user_only_sees_their_own_incidents(client, app):
    with sqlite3.connect(app.config["DATABASE"]) as connection:
        connection.execute(
            "INSERT INTO users (username, password_hash, role) VALUES (?, ?, ?)",
            ("otro_usuario", generate_password_hash("other-password"), "usuario"),
        )
        other_user_id = connection.execute(
            "SELECT id FROM users WHERE username = ?", ("otro_usuario",)
        ).fetchone()[0]
        connection.execute(
            "INSERT INTO incidents (user_id, observation) VALUES (?, ?)",
            (other_user_id, "Incidencia privada de otra persona"),
        )

    login(client, "usuario", "user-test-password")
    response = client.get("/usuario")
    page = response.get_data(as_text=True)

    assert response.status_code == 200
    assert "Incidencia privada de otra persona" not in page


def test_blank_observation_is_not_saved(client, app):
    login(client, "usuario", "user-test-password")
    with client.session_transaction() as session:
        token = session["_csrf_token"]

    response = client.post(
        "/usuario",
        data={"observation": "   ", "csrf_token": token},
        follow_redirects=True,
    )
    with sqlite3.connect(app.config["DATABASE"]) as connection:
        count = connection.execute("SELECT COUNT(*) FROM incidents").fetchone()[0]

    assert response.status_code == 200
    assert "Escribe una observación" in response.get_data(as_text=True)
    assert count == 0


def test_incident_submission_requires_csrf_token(client):
    login(client, "usuario", "user-test-password")

    response = client.post("/usuario", data={"observation": "Problema de red"})

    assert response.status_code == 400


def create_incident(app, observation, category, priority, status, username="usuario"):
    with sqlite3.connect(app.config["DATABASE"]) as connection:
        user_id = connection.execute(
            "SELECT id FROM users WHERE username = ?", (username,)
        ).fetchone()[0]
        cursor = connection.execute(
            """
            INSERT INTO incidents (user_id, observation, category, priority, status)
            VALUES (?, ?, ?, ?, ?)
            """,
            (user_id, observation, category, priority, status),
        )
        return cursor.lastrowid


def test_technician_sees_incidents_from_all_users(client, app):
    create_incident(
        app,
        "Equipo no enciende",
        "hardware",
        "alta",
        "abierta",
    )
    create_incident(
        app,
        "No hay acceso a la cuenta",
        "cuenta",
        "media",
        "en curso",
        username="tecnico",
    )
    login(client, "tecnico", "technician-test-password")

    response = client.get("/tecnico")
    page = response.get_data(as_text=True)

    assert response.status_code == 200
    assert "Equipo no enciende" in page
    assert "No hay acceso a la cuenta" in page
    assert "usuario" in page
    assert "tecnico" in page


def test_technician_filters_by_category_priority_and_status(client, app):
    create_incident(app, "Hardware urgente abierto", "hardware", "alta", "abierta")
    create_incident(app, "Hardware medio abierto", "hardware", "media", "abierta")
    create_incident(app, "Hardware urgente resuelto", "hardware", "alta", "resuelta")
    create_incident(app, "Red urgente abierta", "red", "alta", "abierta")
    login(client, "tecnico", "technician-test-password")

    response = client.get(
        "/tecnico?category=hardware&priority=alta&status=abierta"
    )
    page = response.get_data(as_text=True)

    assert response.status_code == 200
    assert "Hardware urgente abierto" in page
    assert "Hardware medio abierto" not in page
    assert "Hardware urgente resuelto" not in page
    assert "Red urgente abierta" not in page


def test_technician_rejects_invalid_filter(client):
    login(client, "tecnico", "technician-test-password")

    assert client.get("/tecnico?category=desconocida").status_code == 400
    assert client.get("/tecnico?priority=urgente").status_code == 400
    assert client.get("/tecnico?status=pendiente").status_code == 400


def test_technician_can_correct_category_priority_and_status(client, app):
    incident_id = create_incident(
        app,
        "El equipo no arranca",
        "revisar",
        "baja",
        "abierta",
    )
    login(client, "tecnico", "technician-test-password")
    with client.session_transaction() as session:
        token = session["_csrf_token"]

    response = client.post(
        f"/tecnico/{incident_id}?status=abierta",
        data={
            "csrf_token": token,
            "category": "hardware",
            "priority": "alta",
            "status": "en curso",
        },
        follow_redirects=False,
    )
    with sqlite3.connect(app.config["DATABASE"]) as connection:
        updated = connection.execute(
            "SELECT category, priority, status FROM incidents WHERE id = ?",
            (incident_id,),
        ).fetchone()

    assert response.status_code == 302
    assert response.headers["Location"].endswith("/tecnico?status=abierta")
    assert updated == ("hardware", "alta", "en curso")


def test_technician_cannot_update_incident_with_invalid_values(client, app):
    incident_id = create_incident(
        app,
        "Falla de red",
        "red",
        "media",
        "abierta",
    )
    login(client, "tecnico", "technician-test-password")
    with client.session_transaction() as session:
        token = session["_csrf_token"]

    response = client.post(
        f"/tecnico/{incident_id}",
        data={
            "csrf_token": token,
            "category": "invalida",
            "priority": "media",
            "status": "abierta",
        },
    )
    with sqlite3.connect(app.config["DATABASE"]) as connection:
        category = connection.execute(
            "SELECT category FROM incidents WHERE id = ?", (incident_id,)
        ).fetchone()[0]

    assert response.status_code == 400
    assert category == "red"


def test_user_cannot_update_incidents_from_technician_panel(client, app):
    incident_id = create_incident(
        app,
        "Falla de red",
        "red",
        "media",
        "abierta",
    )
    login(client, "usuario", "user-test-password")

    response = client.post(f"/tecnico/{incident_id}")

    assert response.status_code == 403


def test_technician_update_requires_csrf_token(client, app):
    incident_id = create_incident(
        app,
        "Falla de red",
        "red",
        "media",
        "abierta",
    )
    login(client, "tecnico", "technician-test-password")

    response = client.post(
        f"/tecnico/{incident_id}",
        data={"category": "red", "priority": "media", "status": "abierta"},
    )

    assert response.status_code == 400


def test_technician_update_of_missing_incident_returns_404(client):
    login(client, "tecnico", "technician-test-password")
    with client.session_transaction() as session:
        token = session["_csrf_token"]

    response = client.post(
        "/tecnico/9999",
        data={
            "csrf_token": token,
            "category": "red",
            "priority": "media",
            "status": "abierta",
        },
    )

    assert response.status_code == 404
