import logging
from fastapi import HTTPException
from langchain_core.messages import SystemMessage, HumanMessage

from app.models import QuestionnaireInput, RAGResponse
from app.config import settings

logger = logging.getLogger(__name__)

DISCLAIMER = (
    "⚠️ Esta información es orientativa y no constituye asesoramiento legal. "
    "Para decisiones con impacto legal, consulta con un abogado especializado "
    "en derecho digital."
)

SYSTEM_PROMPT = (
    "Eres LegalDev, un asistente especializado en normativa legal aplicable a proyectos "
    "de software en España y la Unión Europea.\n\n"
    "Tu misión es analizar el contexto de un proyecto de software y explicar qué normativas "
    "legales le aplican, con implicaciones técnicas concretas y accionables para el developer.\n\n"
    "Reglas:\n"
    "- Responde siempre en español\n"
    "- Sé específico y técnico: no digas 'debes cumplir el RGPD', di qué tienes que implementar exactamente\n"
    "- Organiza la respuesta por normativa aplicable\n"
    "- Incluye siempre el disclaimer al final\n"
    "- No inventes normativas que no estén en el contexto proporcionado\n\n"
    "Disclaimer obligatorio al final de cada respuesta:\n"
    '"⚠️ Esta información es orientativa y no constituye asesoramiento legal. '
    'Para decisiones con impacto legal, consulta con un abogado especializado en derecho digital."'
)


def _build_query(input: QuestionnaireInput) -> str:
    parts = [input.tipo_proyecto]

    if input.tiene_usuarios_registrados:
        parts.append("usuarios registrados")

    if input.tipos_datos_personales and "ninguno" not in input.tipos_datos_personales:
        parts.append("tratamiento datos personales")
        parts.extend(input.tipos_datos_personales)

    if input.usuarios_menores:
        parts.append("usuarios menores de edad")

    if input.usuarios_ue:
        parts.append("usuarios Unión Europea")

    if input.transferencia_datos_terceros:
        parts.append("transferencia datos terceros")

    if input.usa_ia:
        ia_text = "inteligencia artificial"
        if input.tipo_ia:
            ia_text += f" {input.tipo_ia}"
        parts.append(ia_text)

    if input.usa_cookies:
        parts.append("cookies")

    if input.monetizacion and input.monetizacion != "ninguna":
        parts.append(input.monetizacion)

    if input.contenido_digital:
        parts.append("contenido digital")

    parts.append("cumplimiento legal España")
    parts.append(input.ccaa)
    parts.append(input.descripcion_breve)

    return " ".join(parts)
