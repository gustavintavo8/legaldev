# Corpus normativo

> Procede del anexo A («Corpus normativo») y del apartado «El corpus normativo» del capítulo de análisis de la memoria del TFG (etiqueta `pre-recorte-2026-11` del repositorio de la memoria, `capitulos/40-anexos.tex` y `capitulos/21-analisis.tex`). Describe el índice vigente: corpus `7a2029a4dfd8`, descargado el 12 de septiembre de 2026, con 13.756 fragmentos. En la memoria queda una tabla de una página con cada norma, su ámbito, su fecha de aplicación y si tiene regla.

## Dónde está cada dato

El anexo A reproducía una tabla que ya existe en este repositorio. El 9 de noviembre de 2026 se compararon las dos fila a fila: los 22 documentos coinciden en páginas, bytes y huella SHA-256. La URL también coincide, salvo la del Código del CCII, que el anexo abreviaba. Por eso aquí no se copia y se remite al original:

| Dato | Dónde está |
|---|---|
| Fuente oficial (URL), páginas, bytes y huella SHA-256 (12 caracteres) de cada PDF, con la fecha de descarga | [`docs/CORPUS_SOURCES.md`](../CORPUS_SOURCES.md) |
| Tipo de cada documento y su título completo | [`README.md`](../../README.md), apartado «Normativas indexadas» |
| Licencias y atribución de los textos de terceros del índice | [`NOTICE.md`](../../NOTICE.md) |
| Lista canónica de ficheros (`REQUIRED_DOCS`) y modelo de embeddings | `app/corpus.py` |
| Metadatos del índice (modelo, versión del corpus y del segmentador, fragmentos, documentos, fecha) | `chroma_db/.index_meta.json` |

Los nombres de fichero se reproducen literalmente, con sus particularidades ortográficas, porque identifican cada normativa. Son el campo `source` de los fragmentos y, sin la extensión, el `stem` de las reglas.

## Totales por tipo

| Tipo | Documentos | Páginas | Fragmentos en el índice |
|---|---|---|---|
| Normativa europea | 10 | 731 | 8.234 |
| Normativa española | 4 | 284 | 2.517 |
| Guía de la AEPD | 7 | 433 | 2.903 |
| Deontología (Código del CCII) | 1 | 17 | 102 |
| **Total** | **22** | **1.465** | **13.756** |

Los 22 PDF suman 31.553.742 bytes (31,55 MB). Las páginas por tipo salen de sumar la columna de `docs/CORPUS_SOURCES.md`. Los fragmentos por tipo proceden de una consulta de solo lectura al índice de producción del 25 de septiembre de 2026 (`datos/metadato_articulo.txt` del repositorio de la memoria).

## Versión del corpus

`.corpus_version` guarda los doce primeros caracteres hexadecimales del SHA-256 de la lista ordenada de pares (nombre, tamaño) de los PDF de `docs/` (`_compute_corpus_version` en `app/ingest.py`). La versión acompaña a cada respuesta de la API y de las herramientas MCP.

Cambia si se añade, se quita o se renombra un documento, o si cambia su tamaño. No cambia si un PDF se sustituye por otro del mismo tamaño en bytes. El contenido de cada PDF lo identifica su propia huella, la de `docs/CORPUS_SOURCES.md`, que permite reconstruir el mismo corpus aunque los PDF no se versionen.

## Notas que no recoge `docs/CORPUS_SOURCES.md`

Las notas del anexo A coinciden con la columna «Nota» de `docs/CORPUS_SOURCES.md`, salvo estas:

- **Código Ético y Deontológico CCII.** Obliga a los colegiados y, por la Ley 2/2007, de 15 de marzo, de sociedades profesionales (art. 9), también a las sociedades profesionales inscritas en el colegio.
- **Directiva de Responsabilidad por Productos con IA.** La Directiva (UE) 2024/2853 considera producto los programas informáticos, también los sistemas de IA (art. 4.1 y considerando 13). Deroga la Directiva 85/374/CEE desde el 9 de diciembre de 2026 (art. 21).
- **Data Governance Act (Reglamento UE 2022-868).** La propuesta COM(2025) 837 lo derogaría. A 10 de octubre de 2026 no se había adoptado.
- **Digital Services Act (Reglamento UE 2022-2065).** Título oficial: «Reglamento (UE) 2022/2065 del Parlamento Europeo y del Consejo, de 19 de octubre de 2022, relativo a un mercado único de servicios digitales y por el que se modifica la Directiva 2000/31/CE (Reglamento de Servicios Digitales)» (DO L 277 de 27.10.2022).
- **Directiva NIS2.** Es la Directiva (UE) 2022/2555, de 14 de diciembre de 2022, que en su título oficial se llama «Directiva SRI 2» (DO L 333 de 27.12.2022).

## Propiedades del corpus que condicionan el análisis

- **Heterogeneidad.** Los documentos van de 17 a 160 páginas y son de dos géneros: normas con considerandos y artículos, y guías explicativas. Un reordenador entrenado para la utilidad de la respuesta prefiere las guías al texto legal, como se midió en la batería de regresión.
- **Vocabulario compartido.** Varios documentos usan los mismos términos («consentimiento», «responsable del tratamiento»). La similitud semántica no basta para decidir cuál aplica a un proyecto, y eso lo deciden las reglas de exclusión e inyección de `app/rag.py`.
- **Corpus estático y versionado.** Cualquier cambio en un PDF obliga a reindexar (`make ingest`) y a repetir la batería de regresión (`make eval`). La decisión de reindexar con los textos consolidados del RGPD, del Reglamento de IA, del Data Act y de la DGA sigue abierta (`docs/CORPUS_SOURCES.md`).
