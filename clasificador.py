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
    "Clasifica la incidencia informática descrita por el usuario. "
    "Elige categoria hardware, software, red o cuenta; prioridad baja, media "
    "o alta; y redacta un resumen de un máximo de 15 palabras. "
    "Usa exclusivamente los valores permitidos por el esquema."
)


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
        base_url=os.environ.get("LMSTUDIO_URL", "http://localhost:1234/v1"),
        api_key="lm-studio",
        timeout=10.0,
        max_retries=0,
    )
    modelo = os.environ.get("LMSTUDIO_MODEL", "local-model")

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
            )
        except OpenAIError:
            logger.warning(
                "No se pudo contactar con LM Studio; la incidencia requiere revisión.",
                exc_info=True,
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
