import logging
from pathlib import Path
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


def _build_user_message(input: QuestionnaireInput, docs: list) -> str:
    lines = [
        "## Contexto del proyecto",
        f"- Tipo: {input.tipo_proyecto}",
        f"- Descripción: {input.descripcion_breve}",
        f"- Usuarios registrados: {input.tiene_usuarios_registrados}",
        f"- Acceso público: {input.acceso_publico}",
        f"- Datos personales: {', '.join(input.tipos_datos_personales)}",
        f"- Usuarios menores: {input.usuarios_menores}",
        f"- Usuarios en UE: {input.usuarios_ue}",
        f"- Transferencia a terceros: {input.transferencia_datos_terceros}",
        f"- Usa IA: {input.usa_ia}" + (f" ({input.tipo_ia})" if input.tipo_ia else ""),
        f"- Usa cookies: {input.usa_cookies}",
        f"- Monetización: {input.monetizacion or 'ninguna'}",
        f"- Contenido digital: {input.contenido_digital}",
        f"- CCAA: {input.ccaa}",
        f"- Es empresa: {input.es_empresa}",
        "",
        "## Normativa relevante recuperada",
    ]

    for i, doc in enumerate(docs, 1):
        source = doc.metadata.get("source", "desconocido")
        lines.append(f"\n### Fuente {i}: {source}")
        lines.append(doc.page_content)

    return "\n".join(lines)


def run_pipeline(input: QuestionnaireInput, state) -> RAGResponse:
    query = _build_query(input)
    logger.info("Running RAG pipeline, query: %s", query[:100])

    docs = state.vectorstore.similarity_search(query, k=settings.top_k_chunks)
    logger.info("Retrieved %d chunks", len(docs))

    messages = [
        SystemMessage(content=SYSTEM_PROMPT),
        HumanMessage(content=_build_user_message(input, docs)),
    ]

    try:
        response = state.groq_client.invoke(messages)
    except Exception as e:
        logger.error("Groq API error: %s", e)
        raise HTTPException(
            status_code=503,
            detail="LLM service unavailable. Please try again later.",
        )

    normativas = list({
        Path(doc.metadata["source"]).stem
        for doc in docs
        if "source" in doc.metadata
    })

    return RAGResponse(
        respuesta_completa=response.content,
        normativas_detectadas=normativas,
        chunks_utilizados=len(docs),
        disclaimer=DISCLAIMER,
    )
