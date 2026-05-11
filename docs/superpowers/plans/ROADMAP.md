# LegalDev — Roadmap de mejoras

> Documento vivo. Marca con `[x]` lo que vayas cerrando, edita lo que cambie de prioridad, añade notas inline. Última actualización: 2026-05-10.

---

## Cómo usar este documento

- `[ ]` pendiente · `[x]` hecho · `[~]` en progreso · `[-]` descartado (con motivo)
- Si una sección queda obsoleta, no la borres — táchala con `~~strikethrough~~` y añade la razón. La trazabilidad de decisiones descartadas es tan útil como la de las cerradas.
- Cuando cierres un P0 o P1, mueve la sección al final, bajo `## Histórico`, con la fecha de cierre.

---

## P0 — Crítico, abordar ya

### 1. Frontend: `colegiado` hardcodeado a null

- [x] Añadir checkbox `colegiado` al formulario web
- [x] Validar que el valor llega al backend (no como `null` por defecto)
- [x] Smoke test manual con `colegiado=true` y proyecto de ingeniero individual

**Diagnóstico:** el backend soporta el campo, los tests lo cubren, la query lo incorpora. Pero la UI no lo expone — `colegiado` siempre llega como `null`. Esto convierte 22 documentos indexados en 21 efectivos: el Código Ético CCII es inalcanzable.

**Por qué urge:** no tiene sentido arreglar el retrieval para CCII (P0.3) si el frontend no permite activarlo. Cualquier mejora downstream se queda dormida.

**Notas:**

```
La API recibe el payload y lo procesa sin error 422 — colegiado: true llega correctamente al backend. Pero el Código Ético CCII no aparece en normativas_detectadas.
Esto confirma exactamente el diagnóstico original: el frontend ya no es el cuello de botella (ese bug está resuelto), pero el CCII sigue siendo inalcanzable por retrieval — los chunks del documento no pasan el umbral de score. Eso es el P0.3 que mencionabas en el roadmap.
```

---

### 2. Output del LLM: de chat informal a documento formal

- [x] Diseñar manualmente la respuesta-tipo ideal para el cuestionario del README
- [x] Reescribir `SYSTEM_PROMPT` para producir estructura fija
- [x] Pedir explícitamente exhaustividad ("no omitir obligaciones por brevedad")
- [x] Pedir ordenación por importancia (tiers explícitos: RGPD/LOPDGDD/EU AI Act → directivas → guías AEPD → CCII)
- [x] Forzar formato de cita con página: `> "[cita]" — {Nombre normativa}, p. {página}`
- [x] Subir `max_tokens` del LLM a 4000 (`groq_max_tokens` en Settings)
- [ ] Validar que el frontend renderiza markdown (encabezados, citas, listas)
- [x] Snapshot test del nuevo `SYSTEM_PROMPT` (SHA256 pinned en `tests/test_rag.py`)

**Estructura implementada:**

1. Sumario ejecutivo (1 línea + 2-3 bullets accionables)
2. Secciones por normativa, ordenadas por tier:
   - **Tier 1**: RGPD, LOPDGDD, EU AI Act
   - **Tier 2**: ePrivacy, LSSI, Ley de Propiedad Intelectual, DSA, NIS2, DORA, CRA, Data Act, Data Governance Act, ENS, Directiva de Responsabilidad por IA
   - **Tier 3**: guías AEPD operativas (7 documentos)
   - **Tier 4**: Código Ético CCII (solo si chunks recuperados vía búsqueda auxiliar)
3. Cada obligación: `> cita` → **Interpretación** → **Implementación** bullets (mínimo 2)
4. Criterio de inclusión: ≥2 chunks para Tier 1-3; ≥1 chunk para Tier 4
5. Sección "Cobertura del análisis": normativas indexadas sin chunks recuperados
6. Disclaimer gestionado por `RAGResponse.disclaimer` (no en el prompt)

**Cambios técnicos realizados (2026-05-11):**

- `app/corpus.py` creado como fuente única de `REQUIRED_DOCS` (importado por `ingest.py` y `rag.py`)
- `INDEXED_NORMATIVAS` derivado de `REQUIRED_DOCS` en `rag.py` para computar `not_retrieved`
- `_build_user_message` ampliado con tercer parámetro `not_retrieved: list[str]`
- `run_pipeline` computa `not_retrieved` tras la guard de 404 y lo pasa al mensaje
- `groq_max_tokens: int = 4000` en `Settings`, cableado a `ChatGroq`
- Snapshot test SHA256: `340ecfb728df6938db4afc31f409dd922148c071ce0d62423656c35edeee109f`

**Notas:**

```
Pendiente: validar renderizado markdown en el frontend (P0.2 item no cerrado).
El frontend recibe respuesta_completa con markdown completo — headers, citas blockquote,
bold, bullets. Hay que verificar que se renderiza correctamente y no se muestra como texto plano.
```

---

### 3. Retrieval para CCII: búsqueda auxiliar (después de P0.1)

- [x] **Bloqueado por P0.1** — no implementar antes
- [x] Añadir `colegiado_k` a `Settings` (default 6, igual que cookies)
- [x] Implementar búsqueda auxiliar con query: `"código deontológico ingeniero informático colegiado responsabilidad profesional"`
- [x] Threshold 0.35 (consistente con el resto)
- [x] Calibrar con los 5 cuestionarios anteriores + uno nuevo con `colegiado=true`
- [x] Tabla antes/después de posiciones de CCII en el ranking

**Diagnóstico:** LOPDGDD entierra a CCII por densidad léxica de "datos personales". Mismo patrón que cookies/AEPD-cookies. Solución estructuralmente idéntica.

**Aviso:** cuando llegue P1.5 (refactor a `AUXILIARY_SEARCHES`), no implementes este caso como `if input.colegiado` separado — va a ser la primera entrada de la nueva estructura.

**Notas:**

```
Hallazgo de calibración (2026-05-11): CCII no aparece en la query principal incluso con
overfetch_k=100 — la query compuesta es demasiado dilutada. El auxiliar es imprescindible,
no un simple desempate de posición.

Tabla antes/después (verified localmente con ChromaDB real):
| Métrica                              | Antes  | Después |
|--------------------------------------|--------|---------|
| CCII en normativas_detectadas        | NO     | SÍ      |
| chunks_utilizados                    | 12     | 14      |
| Top CCII score (query auxiliar)      | —      | 0.7656  |

Query auxiliar validada contra 3 variantes antes de hardcodear.
tools/eval_retrieval.py creado como base de P1.4 (parametrizado, 5 casos).
```

---

## P1 — Importante, próxima sesión

### 4. Eval set de retrieval

- [ ] Crear `tools/eval_retrieval.py`
- [ ] Definir 8-10 cuestionarios representativos en JSON/YAML
- [ ] Para cada uno, anotar las normativas esperadas (ground truth)
- [ ] El script corre el retrieval (sin LLM) y reporta `recall@k` por cuestionario
- [ ] Añadir al CI o al menos al Makefile (`make eval`)

**Por qué:** ya no puedes validar a ojo. Con cookies + CCII tienes dos casos especiales y posiblemente más en el futuro. Cualquier cambio en `_build_query()`, threshold, k, o auxiliares necesita regresión automatizada.

**Coste:** 30-45 min de trabajo. Beneficio: indefinido.

**Notas:**

```
[espacio]
```

---

### 5. Refactor a `AUXILIARY_SEARCHES`

- [ ] Definir estructura: `list[tuple[condition: Callable, query: str, k: int]]`
- [ ] Mover cookies a la nueva estructura
- [ ] Añadir CCII como segunda entrada
- [ ] Iterar en `run_pipeline()` en lugar de `if/elif` encadenados
- [ ] Documentar en docstring cuándo añadir un caso nuevo

**Por qué:** hoy es 1 caso. Mañana 2. En 6 meses puedes tener 5-7 (NIS2, DORA, casos que aparezcan al crecer el corpus). Si cada uno es un `if`, el código se degrada. Hacerlo ahora es preventivo, no especulativo — el segundo caso ya está confirmado.

**Anti-patrón a evitar:** no hagas un sistema de plugins sobreingenierizado. Una lista de tuplas o un `@dataclass` con 3 campos basta.

**Notas:**

```
[espacio]
```

---

### 6. Test de prompt injection que verifique algo

- [ ] El test actual solo comprueba `status_code == 200` — no verifica nada útil
- [ ] Reescribir para verificar que `descripcion_breve` queda envuelta en tags en el user message final
- [ ] Mockear el LLM con respuesta fija y verificar que el pipeline no cambia comportamiento ante input malicioso

**Por qué:** un atacante puede meter `</descripcion_usuario>` y romper el sandbox. El test actual pasa igualmente.

**Notas:**

```
[espacio]
```

---

### 7. Tests para `_build_user_message`

- [ ] Cobertura cero hoy
- [ ] Test: incluye todos los campos del cuestionario
- [ ] Test: incluye número de página cuando existe en metadata
- [ ] Test: envuelve `descripcion_breve` en `<descripcion_usuario>`
- [ ] Test: ordena fuentes por orden de llegada (no aleatorio)

**Por qué:** es donde construyes el contexto que va al LLM. Si alguien rompe el formato, no se entera nadie.

**Notas:**

```
[espacio]
```

---

### 8. Snapshot test del `SYSTEM_PROMPT`

- [ ] Hash SHA256 del prompt completo guardado en test
- [ ] Si cambia, el test falla y obliga a actualizar conscientemente
- [ ] Especialmente importante después de P0.2 (reescritura para output formal)

**Por qué:** te protege contra cambios accidentales del prompt durante refactors. Una línea cambiada en el system prompt puede degradar la calidad de respuestas sin que ningún otro test lo detecte.

**Notas:**

```
[espacio]
```

---

## P2 — Mejora, no urgente

### 9. README desactualizado en "Decisiones técnicas"

- [ ] La sección dice que `descripcion_breve` se concatena al final de la query — ahora va al principio
- [ ] Repasar la sección entera por inconsistencias similares

**Notas:**

```
[espacio]
```

---

### 10. `requirements.txt` → `pyproject.toml`

- [ ] Migrar a `pyproject.toml` con `[project]` y `[project.optional-dependencies]`
- [ ] Separar runtime de dev (pytest, pytest-cov, ruff)
- [ ] Generar lockfile (`uv.lock` o `requirements.lock`)
- [ ] Eliminar pytest de la imagen Docker

**Por qué:** 17 dependencias planas, mezcla runtime/dev en la imagen Docker. Estándar 2026.

**Coste:** 1 sesión. Beneficio: limpieza estructural, imagen más pequeña.

**Notas:**

```
[espacio]
```

---

### 11. Spec original obsoleto

- [ ] `docs/superpowers/specs/2026-05-09-legaldev-design.md` documenta arquitectura que ya no existe
- [ ] **Opción A:** actualizar a la arquitectura actual
- [ ] **Opción B (recomendada):** mover a `docs/archive/` con encabezado "Spec original — la implementación divergió"

**Por qué:** documentos de diseño obsoletos en un repo activo desorientan más de lo que orientan.

**Notas:**

```
[espacio]
```

---

### 12. Comentarios en código sobre auxiliares

- [ ] Añadir comentario en `run_pipeline()` cerca de la lógica auxiliar:
  ```python
  # Búsqueda auxiliar — ver README "Query descriptiva + búsqueda auxiliar por dominio"
  ```

**Por qué:** tres palabras que ahorran 20 minutos de arqueología al próximo lector.

**Notas:**

```
[espacio]
```

---

### 13. Citas con página en el prompt

- [ ] Modificar `SYSTEM_PROMPT` para forzar formato `> "[cita]" — {Nombre normativa}, p. {página}`
- [ ] Probablemente se hace en el mismo PR que P0.2

**Por qué:** estás pasando `page + 1` a `_build_user_message` pero el prompt no pide la página, así que el LLM la omite la mayoría de veces. Para un documento formal, citas con página son no-negociables.

**Notas:**

```
[espacio]
```

---

### 14. Mock residual en `conftest.py`

- [ ] Línea: `mock_vectorstore.similarity_search.return_value = [mock_doc]`
- [ ] Ya no se usa — `similarity_search_with_relevance_scores` reemplazó esto
- [ ] Borrar

**Por qué:** ruido. Limpieza de 30 segundos.

**Notas:**

```
[espacio]
```

---

### 15. SECURITY.md y CONTRIBUTING.md

- [ ] Crear `SECURITY.md` con canal de reporte de vulnerabilidades
- [ ] Actualizar `CONTRIBUTING.md` con sección "Adding a new auxiliary search" (después de P1.5)
- [ ] CONTRIBUTING ya cita `OVERFETCH_K` y `MIN_RELEVANCE_SCORE` pero no `COOKIES_K` ni la lógica auxiliar

**Por qué:** sistema público que toca datos personales en el prompt sin canal de seguridad es una falta seria. CONTRIBUTING desactualizado bloquea contribuciones reales.

**Notas:**

```
[espacio]
```

---

## P3 — Apuntar para v0.2.0+

### 16. Reranker

Para cuando el corpus crezca a 40-50 documentos. Cohere-rerank, bge-reranker, o cross-encoder local sobre los 100 candidatos overfetched. Trabajo de una semana, no de una sesión.

### 17. Caching de respuestas

Hash del input → respuesta cacheada. Redis o `functools.lru_cache`. Útil cuando haya tráfico real.

### 18. Versionado del prompt

`PROMPT_V2 = "..."` + setting `PROMPT_VERSION`. Permite rollback rápido si una versión degrada respuestas. Útil con outputs formales que pueden compararse entre versiones.

### 19. Internacionalización

Hoy solo español. ¿Es producto para España exclusiva o para hispanohablantes con proyectos sujetos a RGPD? Decisión de producto, no técnica.

---

## Síntesis priorizada

**Esta semana:**

1. P0.1 — Frontend expone `colegiado`
2. P0.2 — System prompt reescrito para output formal (incluye P2.13: citas con página)
3. P0.3 — Búsqueda auxiliar para CCII (después de P0.1)

**Próxima sesión:**

4. P1.4 — Eval set de retrieval
5. P1.5 — Refactor a `AUXILIARY_SEARCHES` (aprovecha P0.3 para diseñar la abstracción)
6. P1.6, P1.7, P1.8 — Tests serios

**Limpieza paralela:**

7. P2.9, P2.11 — Documentación obsoleta
8. P2.12 — Comentarios en código
9. P2.14 — Mock residual

**Cuando el proyecto crezca:**

10. P2.10 — `pyproject.toml`
11. P2.15 — SECURITY.md, CONTRIBUTING actualizado
12. P3 — Reranker, caching, i18n

---

## Reflexión

El proyecto está en un punto interesante. Las decisiones técnicas individuales son sólidas y bien justificadas. La arquitectura está madurando — los casos especiales (cookies, próximamente CCII) están pidiendo abstracción común, lo cual es señal sana.

Lo que más preocupa no está en el código: es el desfase entre lo que el sistema **puede hacer** (retrieval rico, contexto de calidad, citas con página, exhaustividad) y lo que el sistema **entrega** (respuesta de chat conversacional). El P0.2 es el cambio que más valor visible añade y paradójicamente el que menos código requiere — solo prompt bien escrito.

El bug del frontend (P0.1) es el recordatorio de siempre: un sistema solo es tan bueno como su interfaz menos pulida. Tienes deontología profesional indexada, retrieval funcional, prompt aceptable, y un `null` hardcodeado lo invalida todo.

Cuando termines P0, el proyecto pasa de "demo técnico bien ejecutado" a "herramienta que un developer realmente usaría".

---

## Histórico

> Mueve aquí las secciones cerradas con su fecha de cierre. Mantén el detalle — la trazabilidad importa.

_(Vacío de momento.)_
