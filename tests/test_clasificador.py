import json
from types import SimpleNamespace

from openai import OpenAIError

import clasificador
from clasificador import CLASIFICACION_REVISAR, Clasificacion, clasificar


class FakeCompletions:
    def __init__(self, contents):
        self.contents = iter(contents)
        self.calls = []

    def create(self, **kwargs):
        self.calls.append(kwargs)
        content = next(self.contents)
        if isinstance(content, Exception):
            raise content
        message = SimpleNamespace(content=content)
        return SimpleNamespace(
            choices=[SimpleNamespace(message=message)]
        )


class FakeClient:
    def __init__(self, contents, model_ids=None):
        self.completions = FakeCompletions(contents)
        self.chat = SimpleNamespace(completions=self.completions)
        self.models_list_calls = 0
        self.models = SimpleNamespace(list=self.list_models)
        self.model_ids = model_ids or []

    def list_models(self):
        self.models_list_calls += 1
        return SimpleNamespace(
            data=[SimpleNamespace(id=model_id) for model_id in self.model_ids]
        )


def patch_client(monkeypatch, client):
    monkeypatch.setenv("LMSTUDIO_MODEL", "modelo-de-prueba")
    monkeypatch.setattr(clasificador, "OpenAI", lambda **_kwargs: client)


def test_clasificar_usa_json_schema_y_configuracion_local(monkeypatch):
    client = FakeClient(
        [
            json.dumps(
                {
                    "categoria": "hardware",
                    "prioridad": "alta",
                    "resumen": "El portátil no enciende",
                }
            )
        ]
    )
    patch_client(monkeypatch, client)
    monkeypatch.setenv("LMSTUDIO_URL", "http://localhost:1234/v1")
    monkeypatch.setenv("LMSTUDIO_MODEL", "modelo-local")

    resultado = clasificar("No arranca el portátil, no enciende ni el led")

    llamada = client.completions.calls[0]
    assert resultado == Clasificacion("hardware", "alta", "El portátil no enciende")
    assert llamada["model"] == "modelo-local"
    assert llamada["temperature"] == 0
    assert llamada["max_tokens"] == 128
    assert llamada["response_format"]["type"] == "json_schema"
    assert (
        "No arranca el portátil, no enciende ni el led"
        in llamada["messages"][0]["content"]
    )
    assert llamada["messages"][1]["content"] == (
        "No arranca el portátil, no enciende ni el led"
    )
    assert client.models_list_calls == 0


def test_clasificar_detecta_modelo_chat_de_lm_studio(monkeypatch):
    client = FakeClient(
        [
            json.dumps(
                {
                    "categoria": "hardware",
                    "prioridad": "alta",
                    "resumen": "El portátil no enciende",
                }
            )
        ],
        model_ids=[
            "text-embedding-nomic-embed-text-v1.5",
            "qwen2.5-coder-14b-instruct",
        ],
    )
    patch_client(monkeypatch, client)
    monkeypatch.delenv("LMSTUDIO_MODEL", raising=False)

    resultado = clasificar("No arranca el portátil, no enciende ni el led")

    assert resultado.categoria == "hardware"
    assert client.completions.calls[0]["model"] == "qwen2.5-coder-14b-instruct"
    assert client.models_list_calls == 1


def test_clasificar_reintenta_salida_invalida(monkeypatch):
    client = FakeClient(
        [
            '{"categoria":"otra","prioridad":"alta","resumen":"Problema"}',
            '{"categoria":"red","prioridad":"media","resumen":"Falla la conexión"}',
        ]
    )
    patch_client(monkeypatch, client)

    resultado = clasificar("No hay conexión a la red")

    assert resultado == Clasificacion("red", "media", "Falla la conexión")
    assert len(client.completions.calls) == 2


def test_clasificar_devuelve_revisar_si_segunda_respuesta_es_invalida(monkeypatch):
    client = FakeClient(["respuesta inválida", "respuesta todavía inválida"])
    patch_client(monkeypatch, client)

    resultado = clasificar("No arranca el equipo")

    assert resultado == CLASIFICACION_REVISAR
    assert len(client.completions.calls) == 2


def test_clasificar_devuelve_revisar_si_modelo_no_responde(monkeypatch):
    client = FakeClient([OpenAIError("LM Studio no disponible")])
    patch_client(monkeypatch, client)

    resultado = clasificar("No arranca el equipo")

    assert resultado == CLASIFICACION_REVISAR
    assert len(client.completions.calls) == 1


def test_clasificar_rechaza_resumen_con_mas_de_quince_palabras(monkeypatch):
    resumen = "uno dos tres cuatro cinco seis siete ocho nueve diez once doce trece catorce quince dieciséis"
    client = FakeClient(
        [
            json.dumps(
                {
                    "categoria": "software",
                    "prioridad": "baja",
                    "resumen": resumen,
                }
            ),
            json.dumps(
                {
                    "categoria": "software",
                    "prioridad": "baja",
                    "resumen": "La aplicación se cierra al iniciarse",
                }
            ),
        ]
    )
    patch_client(monkeypatch, client)

    resultado = clasificar("La aplicación se cierra")

    assert resultado == Clasificacion(
        "software", "baja", "La aplicación se cierra al iniciarse"
    )
    assert len(client.completions.calls) == 2
