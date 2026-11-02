import json
import logging
import os
from dataclasses import dataclass
from typing import Literal

from openai import OpenAI
from openai import OpenAIError

logger = logging.getLogger(__name__)

Categoria = Literal["hardware", "software", "red", "cuenta", "revisar"]
Prioridad = Literal["baja", "media", "alta"]


@dataclass(frozen=True)
class Clasificacion:
    categoria: Categoria
    prioridad: Prioridad | None
    resumen: str | None


CLASIFICACION_REVISAR = Clasificacion(
    categoria="revisar",
    prioridad=None,
    resumen=None,
)

_JSON_SCHEMA = {
    "type": "json_schema",
    "json_schema": {
        "name": "clasificacion_incidencia",
        "strict": True,
        "schema": {
            "type": "object",
            "properties": {
                "categoria": {
                    "type": "string",
                    "enum": ["hardware", "software", "red", "cuenta"],
                },
                "prioridad": {
                    "type": "string",
                    "enum": ["baja", "media", "alta"],
                },
                "resumen": {"type": "string"},
            },
            "required": ["categoria", "prioridad", "resumen"],
            "additionalProperties": False,
        },
    },
}

_SYSTEM_PROMPT = (
    "Eres un clasificador de incidencias informáticas. Clasifica únicamente "
    "la observación del usuario y devuelve los tres campos del esquema. "
    "Usa categoria hardware para fallos físicos de equipos o periféricos, "
    "software para programas y sistemas operativos, red para conectividad "
    "o servicios de red, y cuenta para acceso, credenciales o permisos. "
    "Usa prioridad baja, media o alta según el impacto y la urgencia. "
    "El resumen debe describir el problema en un máximo de 15 palabras. "
    "Ejemplo: 'No arranca el portátil, no enciende ni el led' es categoria "
    "'hardware'. No inventes datos y respeta estrictamente el esquema JSON."
)


def _obtener_modelo(cliente: OpenAI) -> str:
    modelo_configurado = os.environ.get("LMSTUDIO_MODEL", "").strip()
    if modelo_configurado:
        return modelo_configurado

    modelos = cliente.models.list().data
    modelo_chat = next(
        (modelo.id for modelo in modelos if "embed" not in modelo.id.lower()),
        None,
    )
    if modelo_chat is None:
        raise ValueError("LM Studio no anuncia ningún modelo de chat.")
    return modelo_chat


def _parsear_clasificacion(contenido: str | None) -> Clasificacion:
    if contenido is None:
        raise ValueError("La respuesta del modelo no contiene contenido.")

    resultado = json.loads(contenido)
    if not isinstance(resultado, dict):
        raise ValueError("La respuesta del modelo no es un objeto JSON.")

    categoria = resultado.get("categoria")
    prioridad = resultado.get("prioridad")
    resumen = resultado.get("resumen")
    if categoria not in {"hardware", "software", "red", "cuenta"}:
        raise ValueError("La categoría devuelta no es válida.")
    if prioridad not in {"baja", "media", "alta"}:
        raise ValueError("La prioridad devuelta no es válida.")
    if not isinstance(resumen, str) or not resumen.strip():
        raise ValueError("El resumen devuelto no es válido.")
    if len(resumen.split()) > 15:
        raise ValueError("El resumen supera el máximo de 15 palabras.")

    return Clasificacion(
        categoria=categoria,
        prioridad=prioridad,
        resumen=resumen.strip(),
    )


def clasificar(observacion: str) -> Clasificacion:
    cliente = OpenAI(
        base_url=os.environ.get("LMSTUDIO_URL", "").strip()
        or "http://localhost:1234/v1",
        api_key="lm-studio",
        timeout=60.0,
        max_retries=0,
    )

    try:
        modelo = _obtener_modelo(cliente)
    except OpenAIError as error:
        logger.warning(
            "No se pudo consultar LM Studio para obtener un modelo: %s", error
        )
        return CLASIFICACION_REVISAR
    except ValueError as error:
        logger.warning(
            "No se pudo obtener un modelo válido de LM Studio: %s", error
        )
        return CLASIFICACION_REVISAR

    for intento in range(2):
        try:
            respuesta = cliente.chat.completions.create(
                model=modelo,
                messages=[
                    {"role": "system", "content": _SYSTEM_PROMPT},
                    {"role": "user", "content": observacion},
                ],
                response_format=_JSON_SCHEMA,
                temperature=0,
                max_tokens=128,
            )
        except OpenAIError as error:
            logger.warning(
                "LM Studio no pudo clasificar la incidencia con el modelo %s: %s",
                modelo,
                error,
            )
            return CLASIFICACION_REVISAR

        try:
            contenido = respuesta.choices[0].message.content
        except IndexError:
            contenido = None

        try:
            return _parsear_clasificacion(contenido)
        except (json.JSONDecodeError, ValueError) as error:
            if intento == 1:
                logger.warning(
                    "LM Studio devolvió una clasificación inválida tras reintentar: %s",
                    error,
                )
                return CLASIFICACION_REVISAR

    return CLASIFICACION_REVISAR
