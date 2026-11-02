import hmac
import os
import secrets
import sqlite3
from functools import wraps
from pathlib import Path
from typing import Callable, TypeVar

from flask import (
    Flask,
    abort,
    flash,
    g,
    redirect,
    render_template,
    request,
    session,
    url_for,
)
from werkzeug.security import check_password_hash

from clasificador import clasificar
from database import init_db

F = TypeVar("F", bound=Callable)

CATEGORIAS_TECNICO = ("hardware", "software", "red", "cuenta", "revisar")
PRIORIDADES = ("baja", "media", "alta")
ESTADOS = ("abierta", "en curso", "resuelta")


def create_app(test_config: dict | None = None) -> Flask:
    app = Flask(__name__)
    app.config.from_mapping(
        SECRET_KEY=os.environ.get("SECRET_KEY") or secrets.token_hex(32),
        DATABASE=str(Path(__file__).resolve().with_name("incidencias.db")),
        DEMO_USER_PASSWORD=os.environ.get("DEMO_USER_PASSWORD", "usuario123"),
        DEMO_TECHNICIAN_PASSWORD=os.environ.get(
            "DEMO_TECHNICIAN_PASSWORD", "tecnico123"
        ),
        SESSION_COOKIE_HTTPONLY=True,
        SESSION_COOKIE_SAMESITE="Lax",
    )
    if test_config is not None:
        app.config.update(test_config)

    init_db(
        app.config["DATABASE"],
        app.config["DEMO_USER_PASSWORD"],
        app.config["DEMO_TECHNICIAN_PASSWORD"],
    )

    def get_db() -> sqlite3.Connection:
        if "db" not in g:
            connection = sqlite3.connect(app.config["DATABASE"])
            connection.row_factory = sqlite3.Row
            connection.execute("PRAGMA foreign_keys = ON")
            g.db = connection
        return g.db

    @app.teardown_appcontext
    def close_db(_error: BaseException | None = None) -> None:
        del _error
        connection = g.pop("db", None)
        if connection is not None:
            connection.close()

    def csrf_token() -> str:
        token = session.get("_csrf_token")
        if token is None:
            token = secrets.token_urlsafe(32)
            session["_csrf_token"] = token
        return token

    app.jinja_env.globals["csrf_token"] = csrf_token

    def validate_csrf() -> None:
        token = session.get("_csrf_token")
        submitted_token = request.form.get("csrf_token", "")
        if not token or not hmac.compare_digest(token, submitted_token):
            abort(400)

    def login_required(role: str | None = None) -> Callable[[F], F]:
        def decorator(view: F) -> F:
            @wraps(view)
            def wrapped(*args: object, **kwargs: object) -> object:
                if "user_id" not in session:
                    return redirect(url_for("login"))
                if role is not None and session.get("role") != role:
                    abort(403)
                return view(*args, **kwargs)

            return wrapped  # type: ignore[return-value]

        return decorator

    @app.get("/")
    def index() -> str:
        if "user_id" not in session:
            return redirect(url_for("login"))
        endpoint = (
            "technician_dashboard"
            if session.get("role") == "tecnico"
            else "user_dashboard"
        )
        return redirect(url_for(endpoint))

    @app.route("/login", methods=["GET", "POST"])
    def login() -> str:
        if request.method == "POST":
            validate_csrf()
            username = request.form.get("username", "").strip()
            password = request.form.get("password", "")
            user = get_db().execute(
                "SELECT id, username, password_hash, role FROM users WHERE username = ?",
                (username,),
            ).fetchone()

            if user is None or not check_password_hash(user["password_hash"], password):
                flash("Usuario o contraseña incorrectos.", "error")
            else:
                session.clear()
                session["user_id"] = user["id"]
                session["username"] = user["username"]
                session["role"] = user["role"]
                return redirect(url_for("index"))

        return render_template("login.html")

    @app.post("/logout")
    @login_required()
    def logout() -> str:
        validate_csrf()
        session.clear()
        return redirect(url_for("login"))

    @app.route("/usuario", methods=["GET", "POST"])
    @login_required("usuario")
    def user_dashboard() -> str:
        if request.method == "POST":
            validate_csrf()
            observation = request.form.get("observation", "").strip()
            if not observation:
                flash(
                    "Escribe una observación antes de registrar la incidencia.",
                    "error",
                )
            else:
                cursor = get_db().execute(
                    """
                    INSERT INTO incidents (user_id, observation)
                    VALUES (?, ?)
                    """,
                    (session["user_id"], observation),
                )
                incident_id = cursor.lastrowid
                get_db().commit()
                classification = clasificar(observation)
                get_db().execute(
                    """
                    UPDATE incidents
                    SET category = ?, priority = ?, summary = ?
                    WHERE id = ? AND user_id = ?
                    """,
                    (
                        classification.categoria,
                        classification.prioridad,
                        classification.resumen,
                        incident_id,
                        session["user_id"],
                    ),
                )
                get_db().commit()
                flash("Incidencia registrada.", "success")
                return redirect(url_for("user_dashboard"))

        incidents = get_db().execute(
            """
            SELECT created_at, observation, category, priority, summary, status
            FROM incidents
            WHERE user_id = ?
            ORDER BY created_at DESC, id DESC
            """,
            (session["user_id"],),
        ).fetchall()
        return render_template("user_dashboard.html", incidents=incidents)

    @app.get("/tecnico")
    @login_required("tecnico")
    def technician_dashboard() -> str:
        filtros = {
            "category": request.args.get("category", ""),
            "priority": request.args.get("priority", ""),
            "status": request.args.get("status", ""),
        }
        valores_filtro = {
            "category": CATEGORIAS_TECNICO,
            "priority": PRIORIDADES,
            "status": ESTADOS,
        }
        for campo, valor in filtros.items():
            if valor and valor not in valores_filtro[campo]:
                abort(400)

        condiciones = []
        parametros: list[str] = []
        for campo, valor in filtros.items():
            if valor:
                condiciones.append(f"{campo} = ?")
                parametros.append(valor)

        consulta = """
            SELECT incidents.id, incidents.created_at, incidents.observation,
                   incidents.category, incidents.priority, incidents.summary,
                   incidents.status, users.username
            FROM incidents
            JOIN users ON users.id = incidents.user_id
        """
        if condiciones:
            consulta += " WHERE " + " AND ".join(condiciones)
        consulta += " ORDER BY incidents.created_at DESC, incidents.id DESC"
        incidents = get_db().execute(consulta, parametros).fetchall()
        return render_template(
            "technician_dashboard.html",
            incidents=incidents,
            filters=filtros,
            categories=CATEGORIAS_TECNICO,
            priorities=PRIORIDADES,
            statuses=ESTADOS,
        )

    @app.post("/tecnico/<int:incident_id>")
    @login_required("tecnico")
    def update_incident(incident_id: int) -> str:
        validate_csrf()
        category = request.form.get("category", "")
        priority = request.form.get("priority", "")
        status = request.form.get("status", "")
        if (
            category not in CATEGORIAS_TECNICO
            or priority not in PRIORIDADES
            or status not in ESTADOS
        ):
            abort(400)

        cursor = get_db().execute(
            """
            UPDATE incidents
            SET category = ?, priority = ?, status = ?
            WHERE id = ?
            """,
            (category, priority, status, incident_id),
        )
        if cursor.rowcount == 0:
            abort(404)
        get_db().commit()
        flash("Incidencia actualizada.", "success")
        filtros = {
            key: value
            for key, value in request.args.items()
            if key in {"category", "priority", "status"}
        }
        return redirect(url_for("technician_dashboard", **filtros))

    return app
