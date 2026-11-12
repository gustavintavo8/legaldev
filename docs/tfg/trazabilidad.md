# Trazabilidad: requisito → caso de uso → prueba → criterio

> Procede de la matriz de trazabilidad del capítulo de análisis y de la relación entre objetivos y requisitos del capítulo de requisitos de la memoria del TFG (etiqueta `pre-recorte-2026-11` del repositorio de la memoria, `capitulos/21-analisis.tex` y `capitulos/20-requisitos.tex`). En los Documentos técnicos de la memoria cada requisito funcional lleva una columna con su objetivo y otra con su prueba. La matriz completa queda aquí. Pruebas del punto de partida en `main@9f173ce`; pruebas del servidor MCP en `832ac33`.

El texto completo de cada requisito y de cada criterio de aceptación está en [requisitos.md](requisitos.md). La organización de la suite por componente y los requisitos no funcionales que verifica cada grupo de ficheros están en [casos-de-prueba.md](casos-de-prueba.md).

## Objetivos del TFG y sus requisitos

| Objetivo | Paquetes | Requisitos | Criterios |
|---|---|---|---|
| OE1, servidor MCP | PT2 | RF-22 a RF-25; RNF-15, RNF-16 y RNF-18 a RNF-21 | CA-09 |
| OE2, mapeo a controles y evidencias | PT3 | RF-26, RF-27 y RNF-17 | CA-10 |
| OE3, comprobación en CI (opcional; se decide el 1 de marzo de 2027) | PT6 | RF-28 | CA-11 |
| OE4, validación comparativa | PT4, PT5 y PT7 | No añade requisitos funcionales | CA-08 y el diseño de la evaluación (conjunto de prueba congelado, líneas base B1 a B3, cobertura y especificidad del mapeo) |

Los requisitos de OE1 están implementados, probados y desplegados en producción, salvo la medición de latencia de RNF-19. El saneado de RNF-20 se añadió el 12 de noviembre de 2026 y todavía no está en el Space. El modo stdio de RF-22 (un servidor local, que corre en la máquina de quien lo usa) y el tope diario por clave de RNF-21 se añadieron el 12 de noviembre de 2026 y todavía no están en el Space. Los de OE2 y OE3 no están implementados. Si falta tiempo, se recorta primero RF-28. Los requisitos *must* de OE1 y OE2 no se recortan.

> **Pendiente (OE2-mapeo).** Tipificación de las obligaciones, módulo y tabla de mapeo, generador de evidencias, pruebas PP-09 y PP-10 y resultados.

## Matriz de los requisitos funcionales

Las pruebas del punto de partida son los ficheros `tests/test_<nombre>.py`; la columna da el `<nombre>`. Las de RF-22 a RF-25 son las del servidor MCP (`tests/test_mcp_*.py` y `tests/test_service.py`), identificadas por su número PP. Las de RF-26 a RF-28 son pruebas diseñadas y aún sin implementar; su criterio de éxito está en el capítulo de pruebas de los Documentos técnicos.

| Requisito | CU | Pruebas | Criterio |
|---|---|---|---|
| **Punto de partida** | | | |
| RF-01 Cuestionario | 01 | `api` | CA-03 |
| RF-02 Validación | 01 | `models`, `api` | CA-04 |
| RF-03 Consulta | 01 | `rag` | — |
| RF-04 Recuperación | 01 | `rag`, `metrics` | CA-01 |
| RF-05 Exclusiones | 01 | `rag`, `retrieval_selection` | CA-01 |
| RF-06 Inyecciones | 01 | `rag` | CA-01 |
| RF-07 Reordenación | 01 | `reranker`, `retrieval_selection` | CA-01 |
| RF-08 Informe | 01 | `rag` | CA-03, CA-08 |
| RF-09 Citas | 01 | `rag` (prompt) | CA-03, CA-08 |
| RF-10 Verificación | 01 | `citations` | CA-03 |
| RF-11 Cobertura | 01 | `rag`, `citations` | CA-03 |
| RF-12 Normativas | 02 | `api`, `store` | — |
| RF-13 Estado | 03, 06 | `api`, `concurrency` | — |
| RF-14 Valoración | 04 | `api` | — |
| RF-15 Caché | 01, 07 | `cache`, `api` | CA-05 |
| RF-16 Límite | 01, 04, 07 | `api` | CA-05 |
| RF-17 Claves | 01, 07 | `api_keys` | — |
| RF-18 Reindexado | 05 | `legal_splitter`, `ingest_build` | CA-07 |
| RF-19 Respaldo | 01, 03 | `llm_fallback` | CA-06 |
| RF-20 Guardia | 03, 05, 06 | `lifespan_guard`, `llm_fallback`, `reranker` | CA-06 |
| RF-21 Interfaz web | 01, 03, 06 | Sin prueba automatizada | — |
| **Servidor MCP, OE1 (pasan en local)** | | | |
| RF-22 Servidor MCP | 07 | PP-01, PP-02, PP-07, PP-13 a PP-17 | CA-09 |
| RF-23 Analizar (MCP) | 07, 08 | PP-03 a PP-05, PP-15, PP-18 | CA-09 |
| RF-24 Listar (MCP) | 07 | PP-02 | CA-09 |
| RF-25 Consultar (MCP) | 07 | PP-06 | CA-09 |
| **Propuestos (pruebas diseñadas, no ejecutadas)** | | | |
| RF-26 Mapeo | 07–09 | PP-09 | CA-10 |
| RF-27 Evidencias | 07–09 | PP-10 | CA-10 |
| RF-28 CI | 09 | PP-11, PP-12 | CA-11 |

> **Hecho (PT2-rnf20).** PP-18 pasa en la suite desde el 12 de noviembre de 2026 (`tests/test_mcp_security.py`, con las cargas de `docs/mcp/pp18/cargas.json`); la medición con el modelo real está en `docs/mcp/README.md`.

## Cómo leer la matriz

- **Impacto de un cambio.** Modificar una regla de inyección afecta a RF-06, a CU-01 y a `tests/test_rag.py`, y obliga a repetir la batería de regresión (`make eval`, CA-01).
- **Concentración.** El punto de partida se concentra en `app/rag.py`, que implementa nueve de los veintiún requisitos del prototipo (RF-03 a RF-09, RF-11 y RF-19) con una recuperación que comparten la API y el evaluador.
- **Hueco de verificación.** La interfaz web (RF-21) no tiene prueba automatizada en este repositorio. Las pruebas de la web rediseñada están en el repositorio `legaldev-web` (`src/**/*.test.tsx`).
