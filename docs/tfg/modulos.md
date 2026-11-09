# Módulos, interfaces y algoritmos

> Procede del capítulo de diseño de detalle y de parte del capítulo de arquitectura de la memoria del TFG (etiqueta `pre-recorte-2026-11` del repositorio de la memoria, `capitulos/23-detalle.tex` y `capitulos/22-arquitectura.tex`). Los Documentos técnicos de la memoria conservan la arquitectura, el *pipeline*, la extensión MCP (clases, herramientas, tipificación, mapeo y evidencia) y una línea por módulo. Aquí queda el detalle de bajo nivel del prototipo: módulos y dependencias, estructuras de datos, interfaces, pseudocódigo, metadatos del índice, imagen Docker, métricas y frontend. Salvo indicación, describe `main@9f173ce`; las notas sobre `832ac33` lo dicen expresamente.

El código no se transcribe. Cada elemento se identifica por su fichero y su nombre, y el código de referencia es el de este repositorio.

## Organización del código

En `main@9f173ce` el *backend* es un paquete Python (`app/`) de catorce módulos con una responsabilidad cada uno, repartidos en tres planos:

- **Servicio:** `main.py` y los módulos transversales de caché, métricas e identificador de petición.
- **Dominio:** `rag.py`, `citations.py`, `reranker.py` y `models.py`.
- **Indexación:** `ingest.py` y `legal_splitter.py`, que se ejecutan fuera de línea y la aplicación no importa, y `corpus.py`, que usan tanto la indexación como la aplicación.

| Módulo | Responsabilidad | Líneas |
|---|---|---|
| `rag.py` | Consulta, reglas, recuperación, reordenación, llamada al modelo con respaldo, verificación de citas y ensamblado de la respuesta; contiene el *prompt* del sistema | 615 |
| `main.py` | Aplicación FastAPI: ciclo de vida, puntos de entrada, límite de peticiones, CORS, claves de API, salud y métricas | 252 |
| `ingest.py` | Indexación fuera de línea: lectura de PDF, segmentación, filtro, embeddings e intercambio atómico del índice | 244 |
| `citations.py` | Extracción y verificación determinista de las citas | 159 |
| `models.py` | Modelos Pydantic de entrada y salida y enumeraciones cerradas | 95 |
| `config.py` | Configuración tipada desde variables de entorno y `.env` | 54 |
| `legal_splitter.py` | Segmentación por artículos y considerandos | 46 |
| `metrics.py` | Métricas Prometheus del dominio | 42 |
| `cache.py` | Caché en memoria con caducidad | 33 |
| `corpus.py` | Lista canónica de documentos y modelo de embeddings | 30 |
| `store.py` | Envoltorio de la API interna de ChromaDB y metadatos del índice | 30 |
| `reranker.py` | Carga perezosa, precalentamiento y uso del *cross-encoder* | 22 |
| `middleware.py` | Identificador de petición (`X-Request-ID`) | 15 |
| `__init__.py` | Marca de paquete (vacío) | 0 |
| **Total** | | **1.637** |

Las líneas son no vacías; contando las vacías, el paquete tiene 1.943.

**Módulos añadidos después del punto de partida.** En `832ac33` el paquete tiene ocho módulos más. Los tres de OE2 son esqueletos sin uso en producción.

| Módulo | Responsabilidad (según su cabecera) | Líneas no vacías |
|---|---|---|
| `mcp_server.py` | Servidor MCP (RF-22 a RF-25; RNF-15, RNF-16, RNF-18 a RNF-21; CU-07) | 606 |
| `mcp_guard.py` | Guarda ASGI de `/mcp`, delante del SDK: origen, clave, límite y lectura del cuerpo | 242 |
| `service.py` | Capa de servicio común a la API REST y al servidor MCP | 215 |
| `errors.py` | Excepciones de dominio del motor | 41 |
| `fragments.py` | Identificador y referencia de un fragmento, comunes a la API, MCP y la evidencia | 38 |
| `obligations.py` | Extracción y tipificación de las obligaciones (esqueleto, OE2) | 106 |
| `controls.py` | Mapeo determinista obligación → controles (esqueleto, OE2) | 102 |
| `evidence.py` | Evidencias exportables en JSON y Markdown (esqueleto, OE2) | 140 |

### Dependencias de importación

En `main@9f173ce`:

- `main.py` importa `rag`, `cache`, `store`, `corpus`, `reranker` y `middleware`.
- `rag.py` importa `middleware`, `metrics`, `reranker` y `citations`.
- `ingest.py` importa `legal_splitter` y `corpus`.
- El evaluador (`tools/eval_retrieval.py`) importa `rag`, `store` y `corpus`, y reutiliza la recuperación de la API.
- Casi todos importan `config.py` y `models.py`.

Ningún módulo de dominio importa `ingest.py`. Lo único que la ingesta comparte con la aplicación es la lista de documentos y el nombre del modelo de embeddings, y los dos se definen en `corpus.py`. Al haber una sola definición, el índice y la aplicación no pueden divergir sin que se note.

El dominio sí dependía del marco web. `rag.py` importaba `HTTPException` de FastAPI y la lanzaba en cuatro puntos: sin cobertura, tiempo de recuperación agotado y los dos fallos del modelo. También leía el identificador de petición de `middleware.py`, que se apoya en Starlette. Una segunda vía que llamase a `run_pipeline`, como el servidor MCP, habría recibido errores HTTP. Por eso PT2 los sustituyó por las excepciones de dominio de `app/errors.py`, que cada adaptador traduce.

## Estructuras de datos

La entrada y la salida de la API son modelos Pydantic v2 de `app/models.py`. Las reglas y el resultado de la recuperación son *dataclasses* inmutables de `app/rag.py`.

| Clase (módulo) | Atributos principales |
|---|---|
| `QuestionnaireInput` (`models.py`) | Los 16 campos del cuestionario: `tipo_proyecto` y `ccaa` (enumeraciones), `descripcion_breve` (texto de 500 caracteres como máximo), `tipos_datos_personales` (lista de enumeración), `usa_ia` y `tipo_ia` (enumeración o nulo), `usa_cookies`, `es_empresa` y otros booleanos. Validador: `usa_ia` ⇒ `tipo_ia`. |
| `RAGResponse` (`models.py`) | `respuesta_completa`, `normativas_detectadas`, `chunks_utilizados`, `disclaimer`, `corpus_version` (por defecto `"unknown"`), `llm_model` (por defecto `"unknown"`) y `citas` (`CitationStats`). |
| `CitationStats` (`models.py`) | `total`, `verificadas`, `no_verificadas` (lista de citas truncadas). |
| `FeedbackInput` (`models.py`) | `request_id` (de 1 a 64 caracteres), `rating` (de 1 a 5), `comment` (opcional). |
| `AuxSearch` (`rag.py`) | `condition`, `query`, `k`, `name`. |
| `Exclusion` (`rag.py`) | `condition`, `stem`. |
| `Injection` (`rag.py`) | `condition`, `stem`, `k`. |
| `RetrievalResult` (`rag.py`) | `docs`, `candidates`, `top_score`, `pre_rerank`, `injected_stems`. Es el resultado de `_retrieve`. |

- **Enumeraciones cerradas.** Todo campo con un conjunto finito de valores es un `StrEnum`, y un valor fuera de catálogo se rechaza con 422 antes de llegar al *pipeline*. Así se cerró, el 14 de junio de 2026, la vía de inyección que abría `ccaa` cuando era texto libre y se interpolaba en el mensaje al modelo. Desde entonces la única entrada libre que llega al modelo es `descripcion_breve`.
- **Valores por defecto en la respuesta.** `corpus_version`, `llm_model` y `citas` los tienen para que un cliente antiguo no falle al recibirlos y uno nuevo distinga una respuesta de una versión anterior del servicio.
- **`colegiado` y `es_empresa`.** `colegiado` se refiere a la persona responsable del proyecto. La API lo admite junto con `es_empresa`, aunque la web antigua lo anulaba al marcar este último. Una empresa puede tener un responsable colegiado, y las sociedades profesionales inscritas en el colegio quedan sujetas a su régimen deontológico (Ley 2/2007, arts. 8.4 y 9). El cuestionario no distingue la empresa de la persona jurídica (la consulta traduce `es_empresa` como «persona jurídica») ni recoge el tamaño de la entidad.
- **Reglas como datos.** Cada regla es una instancia de `AuxSearch`, `Exclusion` o `Injection` con una condición sobre el cuestionario y los parámetros de su etapa. Añadir una regla es añadir una entrada a su lista ([`CONTRIBUTING.md`](../../CONTRIBUTING.md)), y ninguna etapa conoce las reglas concretas. Exclusiones e inyecciones nombran la normativa por su `stem`, la raíz del nombre del PDF. Ese mismo valor aparece en `normativas_detectadas` y lo usa el evaluador, de modo que la relación entre una regla y un documento es una igualdad de cadenas que las pruebas pueden comprobar.

## Interfaz de las funciones principales

| Función (módulo) | Firma | Entrada → salida | Errores y efectos |
|---|---|---|---|
| `run_pipeline` (`rag`) | `async (input, state) -> RAGResponse` | Cuestionario validado y estado de la aplicación → informe con cobertura y citas | En `9f173ce`, `HTTPException` 404 (sin fragmentos) y 503 (tiempo agotado, sin modelo); métricas y evento `rag_pipeline` |
| `_retrieve` (`rag`) | `(inp, vs, threshold) -> RetrievalResult` | Cuestionario, índice y umbral → fragmentos finales y diagnóstico | Síncrona y bloqueante; la acota `wait_for` (60 s) |
| `_select_diverse` (`rag`) | `(ranked, top_k, max_per_source) -> list` | Orden del reordenador → hasta `top_k` fragmentos, como máximo `max_per_source` por normativa | Pura |
| `_invoke_llm` (`rag`) | `async (state, messages) -> (str, str)` | Mensajes → texto y modelo que respondió | Respaldo ante cualquier excepción; 503 si fallan ambos; evento `llm_fallback` |
| `_detect_injection` (`rag`) | `(text) -> bool` | Descripción → sospecha de inyección | Solo registra `suspected_injection` |
| `extract_quotes` (`citations`) | `(answer) -> list[str]` | Informe → citas, en orden | Pura; lineal en la longitud del párrafo |
| `verify_citations` (`citations`) | `(answer, docs) -> CitationStats` | Informe y fragmentos → recuentos y citas no verificadas | Pura |
| `split_document` (`legal_splitter`) | `(doc) -> list[Document]` | Página con metadatos → fragmentos, con `article` si se reconoce el encabezado | Pura |
| `main` (`ingest`) | `() -> None` | `docs/*.pdf` → `chroma_db/` con `.corpus_version` y `.index_meta.json` | `SystemExit` si falta un documento o falla el intercambio, tras restaurar el índice anterior |

## Recuperación y selección diversa

`_retrieve` es la única implementación de la recuperación. `run_pipeline` la ejecuta en un hilo bajo un tiempo máximo global, y el evaluador la llama a través de `retrieve_docs_sync`. Tres detalles explican decisiones que de otro modo parecerían arbitrarias:

- **Deduplicación por MD5.** Los candidatos que una búsqueda auxiliar o una inyección devuelve repetidos se descartan comparando el MD5 de su texto (`_content_hash`), no su identificador en ChromaDB, porque el índice contiene fragmentos de texto idéntico con identificadores distintos. Dos fragmentos que solo se solapan no son duplicados y se conservan.
- **Recorte después de excluir.** El recorte a los 25 candidatos que pasan al reordenador se aplica después de filtrar las normativas excluidas, de modo que una exclusión nunca ocupa una de esas plazas.
- **Orden completo.** Al *cross-encoder* se le pide el orden de todos los candidatos, no solo de los 12 primeros, porque la selección diversa lo necesita completo para rellenar las plazas que deja libres el tope por normativa.

`_select_diverse` recorre el orden del reordenador y acepta como máximo 4 fragmentos de una misma normativa. Los que sobrepasan el tope se apartan en lugar de descartarse y, si al final quedan plazas, las ocupan en su orden original. El algoritmo es lineal en el número de candidatos, conserva el orden y devuelve min(k, n) fragmentos.

```text
selección_diversa(ordenados, k, tope):
  si tope <= 0: devolver los k primeros de ordenados
  elegidos := []; apartados := []; por_fuente := {}
  para cada f en ordenados:                     # orden del reordenador
    si |elegidos| = k: romper
    n := raíz(f.source)
    si por_fuente[n] >= tope:
      añadir f a apartados; continuar           # se aparta, no se descarta
    por_fuente[n] := por_fuente[n] + 1
    añadir f a elegidos
  si |elegidos| < k:
    añadir a elegidos los k - |elegidos| primeros de apartados
  devolver elegidos
```

**Ejemplo construido** (no es una medición) sobre dieciséis candidatos ordenados por el reordenador, con k = 12 y tope 4. Reproduce el patrón que mostraba el evaluador antes del tope, cuando una guía divulgativa de la AEPD acaparaba la mitad del contexto.

| Orden | Normativa del fragmento | Corte simple | Con tope 4 | Motivo |
|---|---|---|---|---|
| 1–2 | Privacidad desde el diseño (AEPD) | sí | sí | |
| 3 | LOPDGDD | sí | sí | |
| 4 | Privacidad desde el diseño (AEPD) | sí | sí | 3.º de la fuente |
| 5 | Análisis de riesgos (AEPD) | sí | sí | |
| 6 | Privacidad desde el diseño (AEPD) | sí | sí | 4.º de la fuente (tope) |
| 7 | LOPDGDD | sí | sí | |
| 8–9 | Privacidad desde el diseño (AEPD) | sí | **no** | Sobrepasan el tope: apartados |
| 10 | LOPDGDD | sí | sí | |
| 11 | Deber de informar (AEPD) | sí | sí | |
| 12 | RGPD | sí | sí | |
| 13 | Guía de cookies (AEPD) | no | **sí** | Ocupa la plaza liberada |
| 14 | LOPDGDD | no | **sí** | 4.º de la fuente; completa las 12 |
| 15–16 | LSSI, Análisis de riesgos | no | no | No se alcanzan |
| | **Normativas distintas en el contexto** | **5** | **6** | |

## Llamada al modelo y orquestación

`run_pipeline` enlaza estas etapas:

1. `_detect_injection` (solo registra).
2. `_retrieve` en un hilo, bajo `wait_for(60 s)`. Si se agota: 503.
3. Si no hay fragmentos: 404 «sin cobertura».
4. `_build_user_message` y `SYSTEM_PROMPT`.
5. `_invoke_llm`: modelo principal y, si falla, el de respaldo. Si fallan ambos: 503.
6. Normativas con dos o más fragmentos.
7. `verify_citations`.
8. `RAGResponse` con las secciones de cobertura y de citas.

`_invoke_llm` reintenta con el modelo de respaldo ante cualquier excepción del principal y devuelve el nombre del modelo que respondió, que llega al cliente en `llm_model`. `_content_to_text` concatena los bloques de texto cuando LangChain devuelve el contenido como lista, algo que ocurre con modelos de razonamiento como `openai/gpt-oss-120b`.

Una normativa entra en `normativas_detectadas` solo si aporta al menos dos fragmentos al contexto, el mismo criterio con el que el *prompt* pide abrir una sección, aunque el modelo no siempre la abre. Una normativa con un único fragmento no entra en esa lista ni tiene sección propia, y desde el 6 de noviembre de 2026 la nombra la sección «Cobertura del análisis». Las inyecciones piden dos o tres fragmentos para garantizar el mínimo de dos.

## Segmentación legal

`split_document` se aplica a cada página extraída con `pypdf`. El encabezado de artículo o considerando se reconoce con una búsqueda anticipada (*lookahead*), de modo que al dividir queda al principio de la parte siguiente y se registra en el metadato `article`. Una parte de más de 1.500 caracteres se subdivide y, desde el segundo trozo, lleva el prefijo sintético «Artículo N (cont.): ». Ese prefijo no existe en el PDF y hace que cada trozo sea autodescriptivo para los embeddings, el reordenador y el modelo.

```text
ENCABEZADO := («Artículo» | «Art.» | «Considerando» | «ARTÍCULO») + espacios + dígitos
segmentar(página):
  texto := recortar(página.texto); si texto = "": devolver []
  partes := dividir texto justo antes de cada aparición de ENCABEZADO
  fragmentos := []
  para cada p no vacía en partes:
    meta := copia(página.meta)
    e := ENCABEZADO al inicio de p, o nulo
    si e no es nulo: meta.article := e
    si |p| <= 1500: añadir (p, meta) a fragmentos; continuar
    trozos := división_recursiva(p, tamaño 500, solape 100)   # heredan meta
    para cada trozo t de índice i > 0: si e no es nulo: t.texto := e + " (cont.): " + t.texto
    añadir trozos a fragmentos
  si fragmentos = []: devolver división_recursiva(página, 500, 100)
  devolver fragmentos
```

El diseño tiene cuatro limitaciones, medidas o comprobadas:

- **Encabezados no reconocidos.** El patrón exige la palabra exacta, y `pypdf` extrae «Ar tículo» de los PDF de EUR-Lex. Por eso solo el 10,3 % de los fragmentos lleva artículo, y ninguno de 9 de las 10 normas de la UE, entre ellas el RGPD.
- **Encabezados espurios.** El patrón no exige inicio de línea y reconoce menciones dentro del texto. En las guías de la AEPD, la mención de un considerando o artículo seguida de la llamada a una nota al pie se registra como encabezado. «Considerando 7551» aparece en 11 fragmentos de la guía de análisis de riesgos, y «Artículo 2918» procede de «Artículo 29» y la nota 18. En total, 44 fragmentos, todos de dos guías, llevan un número mayor que 500, imposible en el corpus. El prefijo «(cont.)» propaga el error a los trozos siguientes.
- **Artículos partidos por un salto de página.** Como la segmentación es por página, la continuación de un artículo en la página siguiente forma una parte sin encabezado y sin metadato.
- **Prefijo dentro de las citas.** La verificación compara contra el texto del fragmento, no contra el PDF, así que una cita que incluya el prefijo se verifica. Ocurre en el informe real del 18 de septiembre de 2026, que cita «Artículo 22 (cont.): protección de datos…» atribuido a la LSSI, artículo 22, página 17. La evidencia de OE2 debe quitar el prefijo.

La versión 3 propuesta normaliza los espacios intrapalabra del encabezado antes de dividir, exige que el encabezado empiece una línea y guarda el número como dato aparte para la clave del mapeo. Los cambios se validarán comparando, documento a documento, la proporción de fragmentos con artículo antes y después del reindexado.

> **Pendiente (PT10-segmentador).** Segmentador versión 3 y localización de cada cita en su fragmento, reindexado con el Reglamento de IA modificado por el Reglamento (UE) 2026/1744, nueva medición del metadato de artículo y nueva ejecución de la batería de regresión.

## Verificación de citas

`citations.py` no depende de la red ni de LangChain. El flujo y el criterio de normalización (NFKC, sin espacio en blanco, segmentos de al menos 12 caracteres, tolerancia del 10 % en los extremos) se describen en el capítulo de diseño de los Documentos técnicos. Este es el algoritmo de comprobación:

```text
verificar_citas(informe, fragmentos):
  corpus := unir con "|" los normalizar(f.texto) de los fragmentos  # "|" no sobrevive a normalizar
  no_verificadas := []
  para cada c en extraer_citas(informe):
    segs := [normalizar(s) para cada s en partir_por_elipsis(c)]
    segs := [s en segs con |s| >= 12]
    si segs = [] o algún s de segs no cumple encontrado(s, corpus):
      añadir c[:120] a no_verificadas
  devolver (total, total - |no_verificadas|, no_verificadas)

encontrado(s, corpus):
  si s está en corpus: devolver verdadero
  t := parte_entera(0,10 · |s|)                 # tolerancia en cada extremo
  para a := 0..t:
    para b := 0..t:
      si a = 0 y b = 0: continuar
      núcleo := s[a : |s| - b]
      si |núcleo| < 12: romper
      si núcleo está en corpus: devolver verdadero
  devolver falso
```

Cuatro casos límite completan el diseño:

- **Extracción lineal.** Cuando un párrafo de cita reúne varias líneas, `_split_paragraph` calcula una sola vez las posiciones de los marcadores «comilla de cierre + guion» y avanza por ellos con un puntero. Sustituyó a una versión que reaplicaba la expresión regular sobre un prefijo cada vez mayor y que tardaba minutos ante una respuesta adversa llena de comillas sin guion.
- **Cita sin segmentos útiles.** Una cita sin ningún segmento de doce o más caracteres cuenta como no verificada, que es la opción conservadora.
- **Coste acotado.** Como mucho (t + 1)² búsquedas de subcadena por segmento, donde t es el 10 % de su longitud.
- **Un fragmento por segmento.** Como el separador «|» desaparece al normalizar, un segmento solo puede coincidir dentro de un único fragmento. La verificación sabe si una cita está en el contexto, pero no en qué fragmento; eso lo añadirá `locate_citations` (OE2).

## Ingesta

Las etapas de `app/ingest.py` son comprobación del corpus, lectura de los PDF, segmentación, filtro de ruido, vectorización, construcción aparte con metadatos e intercambio atómico. El procedimiento de uso está en [`CONTRIBUTING.md`](../../CONTRIBUTING.md) («Re-indexing the corpus»). La versión del corpus se explica en [corpus.md](corpus.md).

**SQLite en Windows.** El intercambio atómico depende de dos detalles en Windows, la plataforma de desarrollo, que no permite renombrar un directorio con ficheros abiertos:

- `_release_chroma_handles` vacía la caché global de sistemas de ChromaDB (`SharedSystemClient.clear_system_cache`), que retiene la conexión SQLite aunque se libere el objeto.
- `_swap_dirs` aparta el índice vigente a `chroma_db.old` y reintenta cinco veces, con un segundo de pausa, el renombrado del nuevo. Si no lo consigue, restaura el anterior y termina con instrucciones.

**Filtro de ruido.** Los fragmentos de menos de 40 caracteres se descartan salvo que lleven `article`, para no perder un artículo derogado de una línea.

**Metadatos de cada fragmento:**

| Metadato | Tipo | Contenido |
|---|---|---|
| `source` | texto | Nombre del fichero PDF. Su raíz (sin extensión) identifica la normativa en las reglas, en el evaluador y en `normativas_detectadas`. |
| `page` | entero | Página de origen, indexada desde 0 (se suma 1 al mostrarla en el *prompt*). |
| `total_pages` | entero | Número de páginas del documento. |
| `doc_type` | texto | `normativa_europea`, `normativa_española`, `guia_aepd`, `deontologia` u `otro`. |
| `article` | texto (opcional) | Encabezado del artículo o considerando, solo si el segmentador lo reconoció. Se muestra en el *prompt* («Fuente 2: LSSI.pdf, Artículo 22, p. 17») y exime al fragmento del filtro de longitud. |

## Imagen Docker y despliegue

La imagen se define en el [`Dockerfile`](../../Dockerfile) y el despliegue en el Space se explica en el [`README.md`](../../README.md) («Deploy en Hugging Face Spaces» y «Qué hace make push-space»). Lo que no está escrito allí:

- **Por qué los modelos van en la imagen.** Los pesos de los dos modelos se descargan al construir la imagen en `/tmp/huggingface`, la única ruta escribible en ejecución en un Space. Con `HF_HUB_OFFLINE=1`, el proceso no contacta nunca con `huggingface.co`.
- **Por qué el índice va en la imagen.** El servicio nunca indexa al arrancar, porque la ingesta es un proceso fuera de línea. Su resultado se versiona con Git LFS: unos 86 MB en `9f173ce`, según la suma de los punteros LFS de `chroma_db/` (el `README.md` decía «~100 MB»). A cambio, el arranque solo carga dos modelos y abre una base SQLite.
- **Trazabilidad del despliegue.** Cada imagen desplegada corresponde a un commit identificable de `main`. El *frontend* (repositorio `legaldev-web`) se sirve desde Vercel y solo se acopla al servicio por la constante `API_BASE`. En ejecución, el contenedor necesita un único secreto, `GROQ_API_KEY`, y además `MCP_API_KEYS` desde que se activó el servidor MCP.

## Métricas Prometheus

`prometheus-fastapi-instrumentator` expone en `/metrics` las métricas HTTP genéricas, y `app/metrics.py` añade las de dominio. Eran nueve en `9f173ce`; PT2 añadió la décima.

| Métrica | Tipo | Qué mide |
|---|---|---|
| `legaldev_chunks_retrieved` | histograma | Fragmentos enviados al modelo tras filtrado, reordenación e inyecciones (cubos de 1 a 30) |
| `legaldev_top_score` | histograma | Mejor puntuación de la búsqueda principal (cubos de 0,2 a 1,0) |
| `legaldev_retrieval_duration_seconds` | histograma | Duración de la recuperación, inyecciones incluidas |
| `legaldev_llm_duration_seconds` | histograma | Espera de la respuesta del modelo |
| `legaldev_404_no_coverage_total` | contador | Peticiones sin cobertura |
| `legaldev_aux_search_triggered_total{type}` | contador | Activaciones de cada búsqueda auxiliar (`rgpd`, `cookies`, `colegiado`) |
| `legaldev_llm_fallback_total{reason}` | contador | Respuestas del modelo de respaldo, por clase de error del principal |
| `legaldev_citations_verified_ratio` | histograma | Proporción de citas verificadas por respuesta (cubos 0; 0,25; 0,5; 0,75; 0,9; 1) |
| `legaldev_citations_unverified_total` | contador | Citas no encontradas en los fragmentos |
| `legaldev_analyze_requests_total{via}` | contador | Análisis por vía: `rest` o `mcp` (y `ci` si se ejecuta OE3). Añadida en PT2. |

Los cubos de los histogramas se eligieron para las magnitudes reales. El de fragmentos llega a 30 porque el contexto final oscila entre 4 y 24 en el evaluador. El de puntuación máxima cubre de 0,2 a 1,0 alrededor del umbral de 0,40, y el de citas verificadas tiene un cubo en 0,9 para distinguir «casi todas» de «todas».

El identificador de petición lo fija `RequestIDMiddleware` en una variable de contexto (`contextvars`), de modo que cualquier función del *pipeline* lo lee sin recibirlo como parámetro y sin mezclar peticiones concurrentes. Si el cliente no lo envía, son los ocho primeros caracteres de un UUID4, y vuelve al cliente en `X-Request-ID`.

## Frontend

> **Aviso.** La memoria describía la página estática `index.html` de `legaldev-web` en la revisión `0a1f03c`, anterior al rediseño. Desde el 30 de octubre de 2026 (PR #1 de `legaldev-web`), la rama `master` es una aplicación React con Vite y TypeScript. Lo que sigue es la descripción de la memoria y vale para esa versión antigua. Al final se indica lo comprobado en la nueva.

### Descripción de la memoria (`index.html`, revisión `0a1f03c`)

La página tenía 991 líneas con estilos y *script*, sin proceso de construcción, y se publicaba en Vercel con una regla de reescritura. Tenía seis secciones (navegación, cabecera con el estado de la API, demostración, «Cómo funciona», pila tecnológica y pie con un aviso de no asesoramiento) y dos puntos de ruptura para móviles. Su única dependencia de JavaScript era `marked`, cargada desde jsDelivr sin versión fija ni integridad de subrecursos, que convertía el Markdown del informe en HTML. Los interruptores eran casillas ocultas visualmente bajo un control dibujado con CSS, accesibles por teclado.

**Campos del formulario.** Exponía nueve de los 16 campos y fijaba los otros siete con los valores del proyecto típico del usuario objetivo:

| Campo | Valor que enviaba la web |
|---|---|
| `tiene_usuarios_registrados` | `true` |
| `acceso_publico` | `false` |
| `usuarios_menores` | `false` |
| `usuarios_ue` | `true` |
| `transferencia_datos_terceros` | `false` |
| `monetizacion` | `null` |
| `contenido_digital` | `false` |

Además, `tipos_datos_personales` tenía siete casillas (sin `biometricos`) y enviaba `["ninguno"]` si no se marcaba ninguna. `tipo_ia` solo era visible si se usaba IA (sin `vision` ni `otro`), y `colegiado` enviaba `true` o `null`, nunca `false`; al marcar `es_empresa`, se desmarcaba y desactivaba.

El modelo recibía esos siete valores como hechos del proyecto («Usuarios menores: False», «Transferencia a terceros: False»), y el informe no decía qué se había supuesto. Una aplicación para menores, o con un proveedor fuera del Espacio Económico Europeo, recibía así un informe construido sobre la premisa contraria. Por esos valores fijos, desde la web la inyección de la LSSI solo se activaba por la vía de las cookies, porque `acceso_publico` era siempre falso. La enumeración de comunidades autónomas del *backend* lleva un comentario que obliga a mantener sus literales iguales a los del `<select>` de la página.

**Estado de la API.** Al cargar, la página consultaba `/health` con un tiempo máximo de ocho segundos y mostraba uno de tres estados: «API online · N docs indexados», donde N era en realidad el número de fragmentos; «Despertando...», si se agotaba el tiempo, porque el contenedor de Hugging Face Spaces se suspende tras un periodo de inactividad; y «API offline». Bajo el formulario, un aviso fijo decía que la primera consulta podía tardar 40–60 s; era texto de la página, no una medición.

**Seguridad y textos.** Los errores de la API y las insignias de normativas se insertaban escapados, pero el informe se convertía con `marked.parse` y se insertaba con `innerHTML` sin sanear. Una cadena adversa que sobreviviera al *prompt* llegaría al navegador como marcado, un riesgo para la seguridad del tratamiento (art. 32 del RGPD). La página publicada conservaba además tres textos inexactos: decía que había «16 documentos legales indexados» (son 22), anunciaba el modelo `llama-4-scout` (retirado el 17 de julio de 2026) y afirmaba que analizaba el ENS, que el motor excluye siempre. La revisión `24ce717` de `legaldev-web` corregía esos textos, fijaba `marked` con integridad de subrecursos, mostraba el aviso del campo `disclaimer` encima del informe y enumeraba junto al formulario los siete valores fijos.

### Lo comprobado en la versión React (`master`, `92b586f`, 9 de noviembre de 2026)

- El informe se convierte con `marked` y se sanea con DOMPurify antes de insertarlo (`src/lib/markdown.ts`).
- `marked` está fijado en `package.json`, y las tipografías se sirven desde el propio sitio con `@fontsource`; el código no carga recursos de Google Fonts ni de jsDelivr.
- El formulario está en `src/components/Demo.tsx` y los valores por defecto del cuestionario, en `src/lib/payload.ts`. No se ha comprobado si la versión React sigue fijando campos ni si el informe declara los supuestos.
- La documentación de la API (`/docs`) la sirve FastAPI con su configuración por defecto, que carga Swagger UI desde jsDelivr.
- Falta confirmar qué revisión está publicada en Vercel.

> **Pendiente (C-26).** Enviar «no consta» en los campos no indicados y abrir el informe con los supuestos del análisis. Hay que comprobarlo contra la versión React.
>
> **Pendiente (C-29).** Sanear el HTML del informe, servir desde el propio sitio las tipografías, `marked` y Swagger UI con versión fija e integridad, y publicar la revisión corregida de la página. En `master` de `legaldev-web` parecen resueltos el saneado, las tipografías y `marked`. Quedan Swagger UI en `/docs` y la confirmación de lo publicado.
