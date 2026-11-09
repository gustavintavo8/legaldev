# Decisiones del prototipo

> Procede del apartado «Componentes del punto de partida» del capítulo de alternativas de la memoria del TFG (etiqueta `pre-recorte-2026-11` del repositorio de la memoria, `capitulos/04-alternativas.tex`). La memoria conserva una tabla con una fila por componente: alternativas, criterio, elección y evidencia. Aquí queda el razonamiento de cada decisión, que se tomó al construir el prototipo previo al TFG (mayo a septiembre de 2026, `main@9f173ce`).

El [`README.md`](../../README.md) ya cuenta buena parte de estas decisiones en su apartado «Decisiones técnicas», y las mediciones del reordenador en «Limitaciones conocidas». Se citan en cada caso y no se repiten. Este documento añade las alternativas que se descartaron, el criterio que decidió y los límites de cada decisión.

Los criterios son los seis del capítulo de alternativas de la memoria: calidad de la recuperación, coste de operación, latencia y recursos del alojamiento gratuito, complejidad operativa, reproducibilidad y riesgo de dependencia de terceros. Cada decisión indica si se basó en una medición o en un razonamiento cualitativo.

## Modelo de embeddings

**Alternativas.** Cuatro modelos de *sentence-transformers*:

- `all-MiniLM-L6-v2`, de unos 80 MB y entrenado sobre todo en inglés. Fue el de la primera versión.
- `paraphrase-multilingual-MiniLM-L12-v2`, el previsto en el diseño inicial.
- `BAAI/bge-m3` y `multilingual-e5-small`, orientados a recuperación y no evaluados sobre el corpus.

**Railway.** El modelo multilingüe hacía caer el proceso en el nivel gratuito de Railway, limitado a 512 MB. Según el `README.md`, ocupa unos 500 MB en memoria; es una cifra estimada, no medida. Al migrar a Hugging Face Spaces el límite desapareció. El cambio de modelo se redujo entonces a una línea y una reindexación, obligatoria porque los vectores de dos modelos no son comparables (`README.md`, «paraphrase-multilingual-MiniLM-L12-v2 en vez de all-MiniLM-L6-v2»).

**`normalize_embeddings`.** El modelo multilingüe no normaliza sus vectores, y la puntuación de relevancia de `langchain-chroma` solo tiene sentido con vectores unitarios. Por eso todos los embeddings del proyecto se instancian con `normalize_embeddings=True` (`README.md`, «Score threshold como guardia anti-alucinación»). Con vectores unitarios, la distancia que devuelve ChromaDB en su espacio `l2` es la euclídea al cuadrado, d = 2 · (1 − cos θ). La puntuación s = 1 − d/√2 equivale entonces a s = 1 − √2 · (1 − cos θ), y el umbral de 0,40 corresponde a un coseno de unos 0,58.

**Decisión y límite.** Se mantiene `paraphrase-multilingual-MiniLM-L12-v2`. Entre los dos MiniLM decidió la memoria del alojamiento, y el multilingüe se adoptó en cuanto cupo. Frente a los dos orientados a recuperación no hay comparación. El motivo que consta en la documentación del repositorio es el coste de reindexar el corpus y repetir la batería de regresión y el barrido del umbral.

El modelo actual es de paráfrasis, no de recuperación asimétrica consulta-documento. En la búsqueda densa el RGPD aparece en posiciones tan bajas como la 44 para consultas básicas de protección de datos (análisis del tercer *sprint*), y las reglas de exclusión e inyección compensan esa debilidad. Compararlo con un modelo orientado a recuperación exige anotar los fragmentos pertinentes de cada caso, como hará el conjunto de prueba de OE4, y queda diferido.

## Reordenación de candidatos (fp32)

**Alternativas.** Sin reordenador; *cross-encoder* `BAAI/bge-reranker-base` en coma flotante (fp32); el mismo cuantizado a int8; reordenación por el propio modelo de lenguaje.

**Criterio y evidencia.** El reordenador se incorporó en la versión 0.2.0, porque los primeros candidatos por similitud mezclaban artículos de normas de vocabulario parecido. Su coste es la latencia: 17,6–20,5 s con 2 hilos, el nivel aproximado del Space gratuito, y 6,5–8,3 s con 6 hilos en el portátil de desarrollo. La cuantización int8 acelera 1,6 veces con 2 hilos (11,06 s frente a 17,58 s por consulta), pero cambia los fragmentos que forman el contexto y se descartó con datos (`README.md`, «Limitaciones conocidas», «Latencia del reranking»). La reordenación por el modelo de lenguaje duplicaría el coste y la latencia de la única llamada remota y rompería la reproducibilidad.

**Decisión.** *Cross-encoder* en fp32, precargado al arrancar y aplicado al conjunto completo de candidatos. Se añade un tope de 4 fragmentos por normativa, porque antes una sola guía de la AEPD solía ocupar cinco o seis de los 12 fragmentos del contexto (`README.md`, «Exclusiones antes del reranker y tope por fuente»).

## Proveedor y modelo de lenguaje (cuota de Groq)

**Alternativas.** API de OpenAI (pago por token), API de Groq (con nivel gratuito) y un modelo abierto ejecutado en el propio servidor.

**Criterio.** Decidieron el coste nulo y los recursos. En el contenedor gratuito, el modelo de embeddings y el reordenador ya ocupan la CPU compartida, y un modelo de lenguaje de tamaño útil no cabe ni en memoria ni en tiempo de respuesta. OpenAI añadiría un coste por consulta indefinido para un servicio público.

**Cuota.** Según el `README.md` («Groq en vez de OpenAI»), Groq ofrecía en el momento de la decisión 500.000 tokens diarios sin coste. A 25 de septiembre de 2026, su plan gratuito admite para `openai/gpt-oss-120b` y `openai/gpt-oss-20b` 30 peticiones por minuto, 1.000 peticiones al día, 8.000 tokens por minuto y 200.000 tokens al día (console.groq.com/docs/rate-limits). No se compararon otros proveedores con nivel gratuito.

**Cambio de modelo.** Groq retiró `meta-llama/llama-4-scout-17b-16e-instruct` el 17 de julio de 2026, y el sustituto es `openai/gpt-oss-120b`. A raíz de la retirada se añadieron tres defensas: comprobar al arrancar que el modelo existe, recurrir a `openai/gpt-oss-20b` ante cualquier excepción y declarar en cada respuesta qué modelo la generó. El respaldo es del mismo proveedor, así que mitiga la retirada de un modelo, pero no la caída del servicio ni un cambio de condiciones.

**Decisión.** Groq con `openai/gpt-oss-120b` y respaldo `openai/gpt-oss-20b`. El riesgo de dependencia de terceros es el mayor del proyecto. Se acepta a cambio del coste nulo y se vigila con `/health/deep` y con la página de retiradas del proveedor (console.groq.com/docs/deprecations).

## Interfaz de entrada

**Alternativas.** Texto libre o cuestionario estructurado con una descripción breve.

**Criterio.** Con texto libre, la recuperación depende de que el usuario emplee el vocabulario adecuado, y la única defensa frente a instrucciones incrustadas en la entrada es el propio modelo. El cuestionario de 16 campos traduce cada respuesta a términos jurídicos que dirigen la búsqueda (`README.md`, «Cuestionario estructurado como interfaz de entrada») y es la base de las reglas de aplicabilidad. Además acota la entrada no fiable a un único campo, `descripcion_breve`, porque los demás son booleanos o enumeraciones cerradas. Ese campo admite 500 caracteres como máximo y va entre etiquetas cuyo contenido el *prompt* del sistema ordena tratar como contexto y no como órdenes. Es una instrucción, no una garantía, y los patrones sospechosos solo se registran.

**Decisión.** Cuestionario estructurado con una descripción breve. La contrapartida es la rigidez: el sistema no usa lo que el cuestionario no captura. El caso más visible es el del DSA, que se analiza en el capítulo de diseño de los Documentos técnicos.

## Segmentación del corpus

**Alternativas.** Bloques de 1.000 caracteres con solapamiento de 200 (diseño inicial), bloques de 500/100 y división por límites de artículo con respaldo por tamaño.

**Criterio y evidencia.** Bajar a 500 caracteres evita que un bloque mezcle dos artículos (`README.md`, «Chunk size 500 en vez de 1000»). El segmentador legal (`app/legal_splitter.py`) corta además por los patrones «Artículo N», «Art. N» y «Considerando N» y subdivide los artículos de más de 1.500 caracteres. Desde su versión 2 anota el metadato `article` y prefija los subfragmentos con «Artículo N (cont.):». Según el `README.md`, fue el cambio individual que más subió el recall, medido sobre el índice anterior. La ingesta descarta los fragmentos de menos de 40 caracteres sin encabezado de artículo.

**Decisión.** Segmentación por artículo con respaldo de 500/100 y filtro de ruido. El patrón no reconoce el encabezado de casi todas las normas de la UE, porque la extracción del PDF parte la palabra «Artículo» (medición en los Documentos técnicos). Corregirlo exige tolerar espacios intercalados, reindexar y volver a medir, con la cobertura de artículos por documento como métrica de la ingesta. Es el paquete PT10.

## Umbral de relevancia: el barrido de mayo

**Alternativas.** Valores entre 0,20 y 0,45 para `MIN_RELEVANCE_SCORE`, y una guardia basada en la puntuación del reordenador, que se midió y se descartó (`README.md`, «Limitaciones conocidas»).

**Barrido inicial.** El valor se fijó con el barrido del evaluador del 15 de mayo de 2026, con 10 casos (`tools/eval_results.md` en el commit `c751584`):

| Umbral | 0,20 | 0,25 | 0,30 | 0,35 | 0,40 | 0,45 |
|---|---|---|---|---|---|---|
| Recall medio | 100 % | 100 % | 100 % | 100 % | 100 % | 100 % |
| Ruido medio | 14,6 | 14,6 | 14,6 | 14,2 | 13,1 | 11,4 |

Esa primera versión del evaluador medía el recall sobre los 100 candidatos de la búsqueda vectorial, sin recorte, reordenador ni exclusiones, por lo que lo sobrestimaba, y aún no medía los falsos positivos. El ruido bajaba al subir el umbral sin pérdida aparente de recall, y el valor pasó de 0,35 a 0,40 para reducirlo (`CHANGELOG.md`, versión 0.2.0).

**Decisión.** Se mantiene 0,40 como filtro grueso y se documenta como guardia débil. El barrido actual, con 13 casos y un evaluador fiel a producción, está en el capítulo de pruebas de los Documentos técnicos.

## Verificación de citas

**Alternativas.** Confiar en el *prompt*, pedir al modelo que se autoverifique en una segunda llamada y comprobar las citas en código.

**Criterio.** La autoverificación se descartó por razonamiento cualitativo: no es determinista, duplica coste y latencia y no admite pruebas unitarias. Un modelo como juez, como en RAGAS, sirve para evaluar fuera de línea, pero no como componente de producción sin coste.

**Decisión.** Verificación determinista en código (`app/citations.py`; `README.md`, «Verificación de citas en código»), con el resultado expuesto en la respuesta (`citas.total`, `citas.verificadas`, `citas.no_verificadas`). No bloquea ni reescribe la respuesta; solo informa al lector de cuánto confiar en cada cita. Convertirla en filtro exigiría medir antes cuántos informes útiles se perderían.

## Infraestructura y proceso

Estas decisiones se tomaron por razonamiento cualitativo, sin probar las alternativas descartadas. La excepción es la de más consecuencias: Railway se probó y se abandonó por Hugging Face Spaces porque el modelo de embeddings multilingüe no cabía en la memoria de su nivel gratuito.

| Decisión | Elección | Descartadas | Criterio y contrapartida |
|---|---|---|---|
| Almacén vectorial | ChromaDB embebido; índice en Git LFS (el Space rechaza binarios fuera de LFS), dentro de la imagen Docker | Pinecone, Qdrant, pgvector | Coste y complejidad: corpus fijo, sin servicio que operar ni pagar. Usa la API privada `_collection`, aislada en `app/store.py`. |
| Framework de la API | FastAPI con Pydantic v2 | Flask; Django REST Framework | Complejidad: validación declarativa del cuestionario, OpenAPI generado y concurrencia asíncrona (`/health` responde durante un análisis). |
| Alojamiento de la API | Hugging Face Spaces con Docker | Railway (abandonado en mayo de 2026); funciones de Vercel | Coste y recursos: memoria para los dos modelos sin coste. Se asumen CPU compartida y arranque en frío tras la inactividad. |
| Interfaz web | Página HTML estática sin *framework*, en Vercel (rediseñada en React el 30 de octubre de 2026) | Streamlit; Next.js | Coste y complejidad: sin construcción ni servidor y desacoplada de la API. Fijaba siete de los 16 campos como constantes ([modulos.md](modulos.md)). |
| Caché de respuestas | Diccionario en memoria con expiración (256 entradas, 3.600 s) | Redis | Complejidad: una sola instancia; con varias, la decisión cambiaría. |
| Límite y acceso | `slowapi` por IP (10 peticiones por minuto); clave `X-API-Key` opcional | Sin límite; clave obligatoria | Coste: protege la cuota del proveedor sin penalizar el uso local; `X-Forwarded-For` solo tras un proxy de confianza. |
| Dependencias | `uv` con `pyproject.toml` y `uv.lock` | pip con `requirements.txt` | Reproducibilidad: CI, imagen y entorno local instalan las mismas versiones. |
| Calidad y pruebas | `ruff`; `pytest` con cobertura mínima del 80 %; GitHub Actions | flake8, isort y black; `unittest` | Complejidad: una herramienta para análisis y formato; menos andamiaje para los dobles de prueba. |
