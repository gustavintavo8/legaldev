"""Métricas de la evaluación extendida (24-pruebas, «Métricas y escala de valoración» y
«Análisis estadístico»; plan por pregunta en tab:pru-ext-plan).

Funciones puras sobre los registros de ``eval/runs``; ninguna llama al LLM ni al índice. Las
métricas de normativa y de fragmento se restringen a las cuatro fuentes anotadas: el resto de
normativas recuperadas no cuenta ni como acierto ni como falso positivo.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Final

# Stems (nombre de fichero sin .pdf) de las fuentes del conjunto acotado.
ANNOTATED_SOURCES: Final[frozenset[str]] = frozenset(
    {"RGPD", "LOPDGDD", "LSSI", "Guía sobre uso de cookies - AEPD"}
)


def normativa_prf(
    expected: set[str], retrieved: set[str]
) -> tuple[float | None, float | None, float | None]:
    """Recall, precisión y F1 de un caso, restringidos a ``ANNOTATED_SOURCES`` (PI1, PI2).

    Generaliza eq:pru-metricas con la precisión |E ∩ R| / |R|. ``None`` cuando el
    denominador es cero (caso fuera de dominio sin normativas esperadas ni recuperadas).
    """
    # TODO(PT5/PI1): implementar y fijar el tratamiento de las anotaciones «dudosa».
    raise NotImplementedError


def fragment_mrr(ranked_chunk_ids: Sequence[str], relevant: set[str]) -> float:
    """Rango recíproco del primer fragmento pertinente de una normativa aplicable (PI2)."""
    # TODO(PT5/PI2): implementar; definir la identidad de un fragmento (hash de contenido,
    # como rag._content_hash) para que la anotación sobreviva a un reindexado.
    raise NotImplementedError


def citation_verified_rate(total: int, verificadas: int) -> float | None:
    """Tasa de citas verificadas por el verificador (PI4)."""
    # TODO(PT5/PI4): implementar; la clasificación manual de las no verificadas
    # (dos fragmentos, extremos, interior, inexistente) se registra aparte.
    raise NotImplementedError


def mapping_coverage(tipificadas: int, con_control: int, sin_control: int) -> dict:
    """Cobertura del mapeo, proporción «sin control técnico» y sin tipificar (PI5)."""
    # TODO(PT5/PI5): implementar sobre las evidencias de S (resultados en tab:res-oe2).
    raise NotImplementedError


# Controles que acreditan casi cualquier obligación y no cuentan para la especificidad
# (24-pruebas, métrica «Mapeo»); 23-detalle cita también mp.info.1 como genérica.
GENERIC_CONTROLS: Final[frozenset[str]] = frozenset({"A.5.31", "A.5.34"})


def mapping_specificity(controles_por_obligacion: Sequence[Sequence[str]]) -> dict:
    """Especificidad del mapeo (PI5): obligaciones con algún control no genérico y número
    medio de controles por obligación."""
    # TODO(PT5/PI5): implementar; decidir si mp.info.1 entra en GENERIC_CONTROLS.
    raise NotImplementedError


def field_accuracy(inferido: dict, anotado: dict) -> dict[str, float]:
    """Exactitud por campo del cuestionario que infiere un asistente real (PI7).

    Acierto en booleanos y enumeraciones; índice de Jaccard en ``tipos_datos_personales``.
    ``descripcion_breve`` no se compara.
    """
    # TODO(PT5/PI7): implementar; el cuestionario inferido se registra en el cliente (los
    # registros del servidor no guardan la descripción, RNF-04 y RNF-15).
    raise NotImplementedError


def cohen_kappa(
    rater_a: Sequence[str], rater_b: Sequence[str], *, ordinal: bool = False
) -> float:
    """Kappa de Cohen entre el autor y el revisor en un eje de la escala (PI3; CA-08).

    Se calcula por eje: sin ponderar en el jurídico (nominal) y ponderada en el de respaldo
    (``ordinal=True``: respalda > parcial > no_respalda).
    """
    # TODO(PT7/CA-08): implementar y fijar la ponderación del eje ordinal (lineal o cuadrática).
    raise NotImplementedError


def bootstrap_ci(
    values: Sequence[float],
    *,
    n_resamples: int = 10_000,
    alpha: float = 0.05,
    seed: int = 0,
) -> tuple[float, float]:
    """Intervalo de confianza por bootstrap sobre los casos (comparaciones emparejadas)."""
    # TODO(PT5/PI2): implementar con semilla fija para que el resultado sea reproducible.
    raise NotImplementedError


def mcnemar(b: int, c: int) -> float:
    """p-valor de McNemar para la proporción de casos que pasa en cada par de configuraciones."""
    # TODO(PT5/PI2): implementar (versión exacta con 40-60 casos).
    raise NotImplementedError
