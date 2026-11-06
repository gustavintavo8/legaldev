# Servidor MCP de LegalDev

**Estado: implementado, desactivado por defecto.** `POST /mcp` existe cuando
`MCP_ENABLED=true` y `API_KEYS` no está vacía; sin claves no se monta aunque se active
(RNF-15). Requisitos RF-22 a RF-25, RNF-15, RNF-16 y RNF-18 a RNF-21; caso de uso CU-07;
pruebas PP-01 a PP-08 y PP-13 a PP-17 (PP-18 pendiente de RNF-20); criterio CA-09; paquete de
trabajo PT2. Desplegado en el Space de Hugging Face desde el 06/11/2026
(`https://gustavintavo8-legaldev.hf.space/mcp`, con `MCP_API_KEYS` propias; la API REST sigue
abierta para la web).

## Diseño resumido

- Punto de entrada `/mcp` en la misma aplicación FastAPI, con transporte Streamable HTTP sin
  estado, escrito con el SDK oficial de Python **`mcp==2.3.0`** (`MCPServer`). Comparte
  proceso, caché, limitador y claves de API con la API REST a través de la capa de servicio
  común (`app/service.py`): `POST /v1/analyze` y `analizar_proyecto` usan la misma entrada de
  caché.
- Capa fina: las herramientas validan, delegan en el motor a través de `app/service.py` y
  traducen el resultado. No añaden lógica de recuperación ni de generación; la prueba de
  equivalencia PP-05 lo fija como invariante comparando los identificadores de los
  fragmentos, en el mismo orden, con la caché desactivada.
- Tres herramientas, en este orden (tabla `tab:det-mcp-herramientas` de la memoria):

| Herramienta | Requisito | Entrada | Resultado | Anotaciones |
|---|---|---|---|---|
| `analizar_proyecto` | RF-23 | El cuestionario de `POST /v1/analyze` (esquema posprocesado de `QuestionnaireInput`) | Informe en Markdown y contenido estructurado: cuestionario interpretado, normativas, fragmentos, modelo, versión del corpus, citas y, con OE2, obligaciones y sin tipificar | `readOnlyHint` |
| `listar_normativas` | RF-24 | Ninguna | Documentos indexados (identificador, tipo, páginas) y versión del corpus | `readOnlyHint`, `openWorldHint: false` |
| `consultar_obligaciones` | RF-25 | `normativa`, `contexto` (máx. 500 caracteres) | Fragmentos de esa normativa (identificador, página, artículo, texto), en el orden del reordenador, sin llamar al modelo | `readOnlyHint`, `openWorldHint: false` |

Identificadores comunes: la normativa es la raíz del nombre de fichero (`RGPD`); el fragmento,
los 12 primeros hexadecimales del MD5 de su texto (`app/fragments.py`); el artículo, el
número como cadena (nulo si el fragmento no lo tiene, como todos los del RGPD con el índice
actual); la página, en base 1.

## Lo que exige la revisión 2026-07-28

Resumen del [registro de cambios](https://modelcontextprotocol.io/specification/2026-07-28/changelog):

- Sin estado: ni sesiones ni `Mcp-Session-Id`, ni `initialize`/`notifications/initialized`,
  ni `ping`. La versión y las capacidades del cliente viajan en `_meta` de cada petición.
- `server/discover` obligatorio (versiones, capacidades, identidad).
- Cabeceras `MCP-Protocol-Version`, `Mcp-Method` y, en `tools/call`, `Mcp-Name` en cada POST;
  si no coinciden con el cuerpo, 400 con `HeaderMismatch` (-32020). GET y DELETE, 405.
- `resultType` obligatorio (`"complete"` | `"input_required"`); `ttlMs` y `cacheScope` en
  `tools/list`.
- MRTR (`InputRequiredResult`) en lugar de peticiones iniciadas por el servidor. LegalDev no
  lo usa en la primera versión: las herramientas reciben todos sus datos como argumentos.
- Sampling, Roots y Logging, obsoletos. LegalDev no los necesita: llama directamente a la API
  de Groq, que es la migración que recomienda la especificación para Sampling.

Compatibilidad con la revisión 2025-11-25: **servidor de doble era** (decidido en la prueba
de concepto). El SDK clasifica cada petición por sus cabeceras: con `MCP-Protocol-Version`
2026-07-28 aplica la revisión nueva; sin ella (o con una versión anterior en la cabecera), la
de `initialize`. Así funcionan también los asistentes que aún no hablan 2026-07-28, y
ninguna de las dos eras guarda estado (no se emite `Mcp-Session-Id`).

## Seguridad

Quién comprueba qué, en este orden (`mcp_guard.CHECK_ORDER`):

1. `Origin` (RNF-18, `McpGuard`): 403 si viene y no está en `MCP_ALLOWED_ORIGINS`, una lista
   propia de `/mcp` independiente de CORS (que admite `*`; esta lista no) (PP-16).
2. Clave de API (RNF-15, `McpGuard`): siempre obligatoria; 401 sin clave (con
   `WWW-Authenticate: ApiKey header="X-API-Key"`), 403 con una desconocida (PP-07). Las
   claves son las de `MCP_API_KEYS` o, si está vacía, las de `API_KEYS`.
3. Límite (RNF-21, `McpGuard`): solo `tools/call` de `analizar_proyecto`, la única
   herramienta que consume cuota del modelo; mismo cupo (`RATE_LIMIT`) y mismo almacén que la
   API, por resumen SHA-256 de la clave; 429 con `Retry-After` (PP-17). Método y herramienta
   se leen del cuerpo, no de `Mcp-Name`, para que los clientes de la era antigua no se libren.
4. Cabeceras (RNF-16, SDK): 400 con `HeaderMismatch` (-32020) si `Mcp-Method`, `Mcp-Name` o la
   versión de la cabecera no coinciden con el cuerpo (PP-14).
5. Versión y `_meta` (RNF-16, SDK): 400 con `UnsupportedProtocolVersionError` (-32022) y las
   soportadas, o -32602 si faltan la versión o las capacidades del cliente (PP-01).

Después: herramienta desconocida, -32602 (middleware `reject_unknown_tools`); argumentos
inválidos, resultado con `isError` y los campos que fallan, sin repetir los valores (PP-04).
GET y DELETE responden 405 desde la propia ruta; el cuerpo admite como mucho 256 KiB (413).
La guarda solo deja pasar un único objeto JSON-RPC que ella misma pueda leer: JSON roto,
anidamiento excesivo, enteros enormes, claves repetidas y lotes reciben 400 antes del SDK, para
que no haya cuerpos que el SDK ejecute y la guarda no cuente. Las herramientas validan los
argumentos tal como llegan, no la copia que el SDK convierte cuando una cadena parece JSON.

Además: descripciones, títulos, instrucciones y descripciones de campo estáticos, fijados por
una prueba de instantánea (RNF-15); registros sin la descripción libre ni el `contexto`
(PP-08, comprobado a nivel DEBUG en todos los registradores); `structuredContent.cuestionario`
sin `descripcion_breve`; progreso cada 5 s mientras se genera el informe si el cliente envía
`progressToken`, y cancelación de la tarea si cierra el flujo (RNF-19); etiqueta `via` en el
registro del pipeline y en `legaldev_analyze_requests_total`. Pendiente: saneado de la salida
del modelo (RNF-20) y la medición de PP-18 con el modelo real.

## Configuración de clientes

Ejemplos en `clients/`, como en el listado `lst:man-mcp` del manual de instalación de la
memoria. Ninguno lleva la clave escrita: cada cliente la toma de un sitio que no se versiona
(formatos comprobados en la documentación de cada cliente el 25/09/2026).

- VS Code: `clients/vscode.mcp.json` -> `.vscode/mcp.json`. La clave es una variable de
  entrada (`inputs`, `promptString` con `password: true`) que VS Code pide al usuario y
  guarda de forma segura; se referencia como `${input:clave}`.
- Cursor: `clients/cursor.mcp.json` -> `.cursor/mcp.json`. Cursor interpola
  `${env:NOMBRE}` en `url` y `headers`: la clave sale de la variable de entorno
  `LEGALDEV_API_KEY`.
- Claude Code: `clients/claude-code.mcp.json` -> `.mcp.json` (ámbito de proyecto). Claude
  Code expande `${VAR}` y `${VAR:-valor}` en `url` y `headers`: la clave sale de
  `LEGALDEV_API_KEY` y la URL, de `LEGALDEV_URL` si existe. En el ámbito local, el de la
  memoria, basta
  `claude mcp add --transport http legaldev <URL>/mcp --header "X-API-Key: $LEGALDEV_API_KEY"`,
  que guarda la configuración en `~/.claude.json`, fuera del repositorio.

En local, la URL es `http://localhost:8000/mcp`, con `MCP_ENABLED=true` y una clave en
`API_KEYS`. La comprobación se puede hacer con el modo de línea de órdenes de MCP Inspector
(`npx @modelcontextprotocol/inspector --cli --method tools/list --transport http --server-url
<URL>/mcp --header "X-API-Key: $LEGALDEV_API_KEY"`), que debe listar las tres herramientas.

Comprobado el 06/11/2026 con el cliente del propio SDK por HTTP contra el índice real (22
documentos), en las dos eras (`mode="auto"` negocia 2026-07-28; `mode="legacy"`, 2025-11-25):
las tres herramientas, los errores de normativa desconocida y de cuestionario inválido, la
herramienta desconocida (-32602) y las notificaciones de progreso. `consultar_obligaciones`
tarda unos 4 s en CPU (búsqueda y reordenador). Con Groq real (`openai/gpt-oss-120b`), un
`analizar_proyecto` en frío tardó 24,5 s (15,5 s de recuperación en CPU y 9 s del modelo), con
notificaciones de progreso cada 5 s; detectó 6 normativas con 18 fragmentos y 12 de 13 citas
verificadas. La misma llamada desde el cliente de la era antigua salió de la caché común
(0,03 s). El registro no contenía la descripción.

TODO(PT2/CU-07): registrar `/mcp` en VS Code, Cursor y Claude Code con la versión vigente de
cada cliente y anotar qué revisión negocia cada uno; puente o modo `stdio` para los clientes
que solo lo admiten.

## Despliegue en el Space de Hugging Face

El Space (`https://gustavintavo8-legaldev.hf.space`) se despliega con `make push-space` desde
`main` (activado el 06/11/2026 con `main@a80c8b1`). Para activar el servidor MCP, en *Settings → Variables and secrets*: `MCP_ENABLED` =
`true` y `MCP_API_KEYS` con las claves que se repartan (secreto); `API_KEYS` sigue vacía para
la web. Los asistentes se conectan a `https://gustavintavo8-legaldev.hf.space/mcp` con la
cabecera `X-API-Key` (ejemplos en `clients/`). El cupo de `analizar_proyecto` es por clave y
comparte la cuota de Groq con la web.

Comprobado en producción el 06/11/2026, con el cliente del SDK por internet y en las dos eras:
sin clave, 401; con una clave falsa, 403; GET, 405; las tres herramientas con el índice del
Space (22 documentos). `analizar_proyecto` con Groq tardó 20,4 s en la primera llamada (6
normativas, 18 fragmentos, 12 de 13 citas verificadas, informe en `structuredContent`) y 0,29 s
desde la caché al repetirla desde la otra era; `consultar_obligaciones`, unos 3,8 s. La API REST
sigue sin pedir clave (`/v1/analyze` con un cuerpo inválido responde 422, no 401).

## Primera prueba con un asistente real (Claude Code, 06/11/2026)

Cuestionario: aplicación web de una empresa de Madrid, de acceso público, con usuarios
registrados en la UE (también menores), nombre y email, cookies, IA generativa, datos a
terceros, contenido digital y publicidad. Claude Code hizo las preguntas que faltaban, llamó
a `analizar_proyecto` y completó con `consultar_obligaciones`, separando en su respuesta lo
que venía de LegalDev de su conocimiento general. Lo que señaló:

- No veía el informe (corregido: ver «Informe en `structuredContent`»).
- `normativas_detectadas` dejaba fuera la LOPDGDD con menores aunque había un fragmento suyo
  en el contexto (regla de al menos dos fragmentos por normativa), y la guía de la AEPD
  sobre IA no salía con IA generativa y datos personales.
- Ruido en la recuperación del RGPD (una nota al pie del DOUE en una consulta sobre registro
  de usuarios; el art. 28 no salió en ninguna consulta).
- Un fragmento de la guía de IA etiquetado como «Considerando 49127» (son las notas 124 y
  125) y palabras partidas por la extracción de los PDF del DOUE («inf or mación»).

Salvo el primero, son límites conocidos del motor y del índice (reglas, divisor y extracción);
quedan como evidencia para la evaluación y no se tocan aquí porque cambian las cifras medidas.

## Segunda prueba con Claude Code, ya contra el Space (06/11/2026)

Cuestionario: persona física colegiada de Asturias, aplicación web de acceso público con
suscripción, usuarios registrados en la UE (también menores), nombre y email, cookies, IA
generativa y datos a terceros. El asistente preguntó los datos que faltaban («las instrucciones
del servidor piden preguntarlos en vez de suponerlos»), recibió el informe completo y lo
contrastó con cuatro llamadas a `consultar_obligaciones`, separando lo que tenía respaldo en el
corpus de lo que aportaba él. Lo que señaló de LegalDev:

- **Citas no verificadas por los guiones (corregido).** 4 de las 13 citas se rechazaron solo
  porque el modelo escribe el guion de corte de línea como U+2011 (que la normalización NFKC
  convierte en U+2010) donde el PDF tiene «-». `app/citations.py` ignora ahora U+2010,
  U+2011, U+2012, U+2212 y U+2043, como el resto de guiones; la web, que repite esas reglas
  para marcar las citas, también.
- **Normativas con un solo fragmento en ninguna lista (corregido).** Una normativa con un
  único fragmento no llega a `normativas_detectadas` (hacen falta dos) ni a la lista de
  «Cobertura del análisis», que solo recogía las que no tenían ninguno. Esa sección tiene
  ahora dos listas: sin fragmentos en este análisis (con la aclaración de que se pueden
  consultar por separado, porque el asistente la leyó como «el índice no tiene nada») y con
  un solo fragmento.
- **EU AI Act detectada sin sección en el informe** (sin corregir: depende del modelo y del
  prompt). Estaba en `normativas_detectadas` con fragmentos suyos en el contexto.
- **Partes del informe que no conviene seguir** (sin corregir; evidencia para PI8):
  `navigator.cookieEnabled` como gestor de consentimiento, *opt-out* para las cookies no
  técnicas, un plazo de conservación de registros sacado de un fragmento que no trata del
  responsable, un número de clics inventado atribuido al código del CCII, un consentimiento
  explícito para la IA sin respaldo y tres «citas del RGPD» que son considerandos.

## Decisiones de la prueba de concepto (06/11/2026)

- **SDK `mcp==2.3.0`.** Atiende la revisión 2026-07-28 y las anteriores, y valida él mismo
  cabeceras, versión, `_meta` y métodos eliminados; no se reimplementa nada de eso.
- **Doble era.** Ver arriba. Cambia RNF-16 y la prueba que esperaba un 400 para el
  `initialize` de 2025-11-25: ahora se atiende.
- **Orden de las comprobaciones.** El de 23-detalle: `Origin`, clave y límite en una guarda
  delante del SDK; cabeceras y versión, en el SDK. Poner las cabeceras antes que la clave
  (22-arquitectura y CU-07) obligaría a duplicar la validación del SDK.
- **Herramienta desconocida.** El SDK la devuelve como resultado con `isError`; un middleware
  la convierte en el error -32602 que piden `tab:ana-errores-mcp` y PP-04.
- **`Host`.** La comprobación de `Host`/`Origin` del SDK está desactivada: la de `Origin` la
  hace la guarda con su propia lista, y la de `Host` exigiría enumerar los dominios del
  despliegue. Con la clave siempre obligatoria y `Origin` comprobado, el DNS rebinding no
  alcanza a las herramientas.
- **Ruta exacta.** `/mcp` es una ruta, no un `Mount`, que respondería 307 a `/mcp` (el cliente
  del SDK no sigue esa redirección).
- **Validación estricta.** Los argumentos se validan con los modelos Pydantic en modo estricto
  sobre JSON, como el esquema publicado: `"true"` no es un booleano. La API REST sigue en modo
  flexible. PP-02 comprueba que esquema y herramienta dan el mismo veredicto en 11 casos.
- **Esquema publicado.** El de `QuestionnaireInput` con las referencias en línea, una
  descripción por campo (las preguntas del formulario de la web) y `if`/`then` para
  `usa_ia` -> `tipo_ia`. Un cuestionario inválido recibe todos los fallos a la vez, también
  el de `tipo_ia` cuando falla otro campo.
- **Sin cobertura.** Resultado normal con `sin_cobertura: true`, sin normativas y con la lista
  de las indexadas en el texto.
- **`consultar_obligaciones`.** Sin LLM y sin umbral (quien pregunta ya eligió la normativa):
  30 candidatos filtrados por documento, reordenados, 6 devueltos. Identificador exacto,
  sensible a mayúsculas; uno desconocido devuelve la lista de válidos.
- **Clave del límite.** Por clave de API (resumen SHA-256), y por IP solo si no la hubiera
  (inalcanzable con RNF-15). El «tope diario por clave» del modelo de amenazas sigue sin
  concretar.
- **Cupo de `consultar_obligaciones`.** No se limita (RNF-21 solo limita lo que consume cuota
  del modelo), pero ocupa unos 4 s de CPU por llamada. Con la clave obligatoria el riesgo es
  bajo; si hiciera falta, un cupo propio más amplio o un semáforo alrededor de la recuperación.
- **stdio.** Aplazado: `run_stdio` sigue sin implementar.
- **Claves propias de `/mcp` (`MCP_API_KEYS`).** La web pública llama a `/v1/analyze` sin
  clave (una clave en el JavaScript de la web sería pública), así que en producción
  `API_KEYS` tiene que quedar vacía. Para no dejar `/mcp` abierto, tiene su propio conjunto
  de claves; si `MCP_API_KEYS` está vacía, se usan las de `API_KEYS`, como pedía RNF-15.
- **Informe en `structuredContent`.** En la primera prueba con Claude Code (06/11/2026) el
  asistente recibió las normativas, los fragmentos y el recuento de citas, pero no el
  informe: Claude Code solo pasa al modelo el contenido estructurado cuando la herramienta
  declara `outputSchema`, y el informe iba solo en el texto. Desde entonces va también en
  `structuredContent.informe`; el JSON del texto no lo repite.

## Cambios que necesita la memoria

- RNF-16, 21-analisis y la prueba RNF-16 de 24-pruebas: doble era en lugar de rechazar el
  `initialize`; PP-14 solo puede exigir coherencia de cabeceras, no su presencia.
- 22-arquitectura («Flujo sin estado de una invocación») y CU-07 (paso 5): orden de las
  comprobaciones de 23-detalle.
- 04-alternativas y 23-detalle: versión fijada del SDK (2.3.0) y lo que valida por sí mismo.
- 31-manual-usuario (tabla de herramientas), objetivo y flujo 3a de CU-07 y orden de recorte
  de 05-metodologia: `consultar_obligaciones` no redacta obligaciones; devuelve fragmentos.
- 20-requisitos (tercera precisión de la tabla de RF): el esquema publicado sí expresa
  `usa_ia` -> `tipo_ia`.
- RNF-21, 22-arquitectura y 23-detalle: el límite es por clave («o, si no la hay, por IP»),
  como `tab:ana-errores-mcp`.
- 30-manual-instalacion: variables `MCP_ENABLED`, `MCP_API_KEYS` y `MCP_ALLOWED_ORIGINS`, y
  la activación en el Space.
- RNF-15: las claves de `/mcp` pueden ser un conjunto propio (`MCP_API_KEYS`), porque la web
  pública obliga a dejar abierta la API REST.
- tab:det-mcp-herramientas: el contenido estructurado de `analizar_proyecto` lleva el
  `informe`.
- tab:det-mcp-herramientas: el cuestionario devuelto excluye `descripcion_breve`; campo
  `sin_cobertura`.

Siguen abiertas, como estaban: tipificación de las guías de la AEPD sin articulado y forma de
`sin_mapeo` en la evidencia (OE2).

## Acción de integración continua

TODO(PT6/RF-28): repositorio aparte `legaldev-action` (opcional; se decide el 1 de marzo de
2027). Consumirá `POST /v1/analyze` y `POST /v1/evidence`; sus pruebas PP-11 y PP-12 viven
en ese repositorio, no en este.
