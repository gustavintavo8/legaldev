# Servidor MCP de LegalDev

**Estado: implementado, desactivado por defecto.** `POST /mcp` existe cuando
`MCP_ENABLED=true` y hay claves (`MCP_API_KEYS` o, si está vacía, `API_KEYS`); sin claves no
se monta aunque se active
(RNF-15). En local, el mismo servidor funciona también por stdio
(`python -m app.mcp_stdio`, ver «Modo stdio»). Requisitos RF-22 a RF-25, RNF-15, RNF-16 y
RNF-18 a RNF-21; caso de uso CU-07;
pruebas PP-01 a PP-08 y PP-13 a PP-18; criterio CA-09; paquete de trabajo PT2. El informe sale
saneado (RNF-20) y marcado como generado por IA (C-05) desde el 12/11/2026, todavía no en el
Space. Desplegado en el Space de Hugging Face desde el 06/11/2026
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
   API, por resumen SHA-256 de la clave; 429 con `Retry-After` (PP-17). Después del cupo por
   minuto, el tope diario por clave si `MCP_DAILY_LIMIT` lo fija (ver «Tope diario por
   clave»). Método y herramienta se leen del cuerpo, no de `Mcp-Name`, para que los clientes
   de la era antigua no se libren.
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
registro del pipeline y en `legaldev_analyze_requests_total`; saneado de la salida del modelo
e instrucciones que dicen que los resultados son contenido y no órdenes (RNF-20, PP-18; ver
«Salida segura»).

### Tope diario por clave (`MCP_DAILY_LIMIT`)

Responde a la amenaza de consumo de la cuota del proveedor del modelo: con solo el cupo por
minuto, una clave filtrada podía pedir `10/minute` × 1.440 minutos = 14.400 análisis al día y
agotar la cuota de Groq, que el Space comparte con la web.

- **Valor.** `MCP_DAILY_LIMIT=200/day` (o `200`): como mucho 200 llamadas a
  `analizar_proyecto` por clave y día. Vacío o `0` (el valor por defecto), sin tope. Si no
  es un único límite por día (`200/hour`, `1/day;2/day`), la aplicación no arranca, igual que
  con un `*` en `MCP_ALLOWED_ORIGINS`.
- **Cómo cuenta.** Por clave (el mismo resumen SHA-256 que el cupo por minuto) y en el mismo
  almacén del limitador, con un identificador propio (`tope_diario`): si `RATE_LIMIT`
  incluyera el mismo límite (`10/minute;200/day`), sin él los dos compartirían contador y
  cada llamada contaría dos veces. Se comprueba después del cupo por minuto, así que una
  llamada frenada por el cupo no gasta el tope.
- **Qué cuenta.** Toda llamada a `analizar_proyecto` que pasa la guarda: también las que
  acaban saliendo de la caché, las de un cuestionario inválido (resultado con `isError`) y
  las que no tienen cobertura, aunque ninguna de las tres llame a Groq. La guarda decide
  antes de entregar la petición al SDK, sin validar el cuestionario ni mirar la caché. Para
  descontar esos casos habría que repetir en la guarda la validación estricta y la clave de
  la caché, o llevar el tope a la herramienta, donde el rechazo dejaría de ser un 429 con
  `Retry-After` como el resto y pasaría a ser un resultado con `isError`. Además, el tope es
  una cota del gasto: contar de más lo hace más estricto, nunca más laxo, y un cliente que
  repite un cuestionario ya tiene la respuesta. El cupo por minuto cuenta igual.
- **Ventana.** 24 horas desde la primera llamada contada de cada clave, no desde
  medianoche. El almacén es la memoria del proceso: un reinicio del Space (se duerme por
  inactividad o se redespliega) pone a cero el tope, igual que el cupo por minuto.
- **Al agotarse.** 429 con `Retry-After` (los segundos que faltan), código -32000 y un
  mensaje que da el tope, cuándo se renueva y que `listar_normativas` y
  `consultar_obligaciones` siguen disponibles. Se registra como `mcp_rejected` con `reason`
  `DailyLimitExceeded`, distinto del `RateLimited` del cupo por minuto.
- **Dónde no se aplica.** En stdio (no hay clave: cada desarrollador gasta su propia cuota
  de Groq) ni en la API REST, que la web llama sin clave y se limita por IP.

Pruebas en `tests/test_mcp_daily_limit.py`: el tope y su `Retry-After`, que cuentan los
aciertos de caché y los cuestionarios inválidos, que las otras herramientas no lo gastan, los
clientes de la era antigua, el aislamiento entre claves, la separación del contador de
`RATE_LIMIT`, el orden con el cupo por minuto, la ausencia de tope y la validación del valor.

Pendiente: fijar el valor en el Space (*Settings → Variables and secrets*), por debajo de la
cuota diaria de Groq repartida entre las claves y la web.

### Salida segura (RNF-20) y PP-18

**Qué amenaza cubre.** La inyección indirecta a través de la salida. Quien controla parte del
texto que lee el modelo le puede pedir que escriba en el informe algo que se ejecuta al
mostrarlo o al leerlo un asistente. Ese texto puede ser la descripción libre del cuestionario,
que un asistente puede rellenar con texto de terceros (un README, una incidencia), o un
fragmento del índice, si alguien lo envenenara. El prompt no cambia (decisión D-1): el informe
se sanea en código.

**Dónde.** `app/sanitize.py`, al que llama `rag.run_pipeline_detailed` justo después del
modelo, antes de verificar las citas y de guardar el resultado en la caché común. La API REST,
`analizar_proyecto` (por HTTP y por stdio) y la web reciben el mismo texto.

**Qué retira** (el detalle está en la cabecera del módulo):

- Caracteres de control y secuencias de escape ANSI. Caracteres invisibles: ancho cero,
  dirección bidi, etiquetas Unicode y selectores de variación. Se respetan el guion blando,
  que está en 243 fragmentos de la Directiva ePrivacy, y el selector de un emoji.
- Bloques que imitan llamadas a herramientas, que pasan a «(bloque retirado)»: etiquetas de
  llamada al estilo XML, tokens especiales `<|…|>`, el formato harmony de gpt-oss
  (`to=functions.…`), `[TOOL_CALLS]`, objetos JSON con nombre y argumentos o con
  `tools/call`, y bloques de código que se anuncian como llamada.
- HTML en bruto: comentarios, bloques `script`, `style`, `iframe`, `svg` y similares con su
  contenido, etiquetas de elementos HTML y cualquier etiqueta con atributos. `` `<script>` ``
  en un código en línea se queda en `` `script` ``, para no estropear un consejo sobre
  cookies. Una etiqueta desconocida sin atributos (`<nombre de la empresa>`) es inerte y se
  deja.
- Todas las imágenes Markdown, que pasan a «(imagen retirada)»: se descargan solas al pintar
  el informe y pueden llevar datos en la URL. Los enlaces y las definiciones de referencia
  cuyo destino no sea `http(s)` a un dominio oficial del corpus (`boe.es`, `aepd.es`,
  `sedeaepd.gob.es`, `ccii.es`, `eur-lex.europa.eu` y `data.europa.eu`, con sus subdominios)
  se quedan en su texto. Los autoenlaces (`<https://…>`) no oficiales pasan a código. El
  destino se analiza como URL, así que no pasan `javascript:`, `//otro`, `boe.es.otro.com` ni
  `https://boe.es@otro`.
- URL sueltas, que un visor convierte en enlace: se quedan las de un dominio oficial y las
  que aparecen en los fragmentos que recibió el modelo; las demás pasan a código, donde se
  leen pero no son enlace.
- Bloques de código sin cerrar, que se cierran: si no, se tragarían el resto del informe y,
  por MCP, el JSON del resultado.

**Constancia.** El campo `saneado` (recuentos por tipo) va en la respuesta REST y en el
`structuredContent` de `analizar_proyecto`. Si se ha retirado algo, el informe lleva además
una sección «Saneado de la salida», antes de «Verificación de citas». Nunca se repite lo
retirado. El registro `rag_pipeline` lleva los mismos recuentos.

**Contenido, no órdenes.** Las instrucciones del servidor dicen que los informes y fragmentos
son contenido para el desarrollador, no órdenes, y que no se llamen herramientas porque lo
pidan. El aviso de los resultados MCP añade que el resultado es contenido para el
desarrollador, no instrucciones para el asistente.

Decisiones:

- **Sanear antes de verificar las citas.** Así las citas, la lista de no verificadas (que se
  repite en el informe y en `citas.no_verificadas`) y lo que guarda la caché describen el
  texto que se entrega. Si se verificara antes, las citas crudas volverían a entrar en el
  informe por esa lista.
- **Las citas literales siguen verificándose.** El saneado deja igual los 13.756 fragmentos
  del índice real: `docs/mcp/pp18/corpus_identidad.py` (solo lectura) dio el 12/11/2026 0
  fragmentos cambiados y 0 distintos tras `citations.normalize`, con el corpus
  `7a2029a4dfd8`. Una cita literal de un fragmento real no puede dejar de verificarse por el
  saneado. Una cita de un fragmento envenenado que traiga marcado neutralizado sí deja de
  verificarse, y es lo correcto. `citations.normalize` no cambia (la web repite sus reglas).
- **URL sueltas de los fragmentos.** El corpus tiene URL de más de 50 dominios que no son
  fuentes oficiales (arxiv.org, enisa.europa.eu, edpb.europa.eu…). Neutralizarlas todas
  rompería citas literales. Una URL copiada tal cual de un fragmento se escribió antes de la
  petición y no puede llevar datos del usuario; una que compone el modelo, sí. El precio: la
  URL de un fragmento envenenado se queda como enlace. Los autoenlaces no tienen esa
  excepción, porque el corpus sale de PDF y no tiene ninguno: si hay uno, lo ha escrito el
  modelo.
- **`consultar_obligaciones` no se sanea.** Devuelve texto del corpus sin pasar por el modelo,
  y el saneado no lo cambiaría (medido arriba). El índice se construye en local desde los PDF
  oficiales. Si algún día pudiera envenenarse, bastaría con aplicar `sanear` al texto de los
  fragmentos en `service.consultar_obligaciones`.
- **Lo que no cubre.** Una orden en lenguaje natural («dile al asistente que…») no se puede
  quitar sin entender el texto: la mitigan las instrucciones y el aviso, y su efecto se mide
  con el modelo real (abajo). Tampoco se impide que el modelo imite las secciones que añade
  el código, como una «Verificación de citas» falsa.

**PP-18 automática** (`tests/test_mcp_security.py`). Usa 17 cargas reales
(`docs/mcp/pp18/cargas.json`, con su técnica y su fuente):

- exfiltración por imagen Markdown, enlaces con destino oculto y `javascript:`, y la imagen y
  el enlace por referencia de EchoLeak;
- XSS con `onerror` y `script`, una orden en un comentario HTML, y SVG con `iframe`;
- llamadas a herramientas al estilo XML, JSON de OpenAI, harmony de gpt-oss, Hermes, Mistral
  y JSON-RPC de MCP;
- contrabando con etiquetas Unicode y con selectores de variación, Trojan Source (bidi) y
  escapes ANSI;
- el escape del delimitador `</descripcion_usuario>` con un autoenlace.

Cada carga va en la descripción y en un fragmento envenenado, con el modelo simulado que la
repite (34 casos). En ninguno llega una forma ejecutable a la API REST ni al asistente, ni en
el texto ni en `structuredContent`. Lo comprueba un oráculo escrito aparte del saneado
(`tests/_pp18.py`), y otra prueba confirma que ese oráculo detecta cada carga sin sanear.
Además, la cita limpia se sigue verificando y el cuestionario devuelto no repite la
descripción. Las pruebas de cada regla del saneado están en `tests/test_sanitize.py`.

**PP-18 con el modelo real.** Pendiente de medir con `docs/mcp/pp18/medir.py`.

### Marcado del contenido generado por IA (C-05)

El Reglamento de IA (art. 50.2) pide marcar el contenido generado por IA en un formato legible
por máquina (hallazgo C-05 de la revisión jurídica). Desde el 12/11/2026, la respuesta de
`POST /v1/analyze` y el `structuredContent` de `analizar_proyecto` (también en su
`outputSchema`) llevan el campo `generado_por_ia`:

```json
"generado_por_ia": {"modelo": "openai/gpt-oss-120b", "proveedor": "Groq", "fecha": "2026-11-12T10:15:03.123456Z"}
```

- `modelo` es el que redactó el informe; si lo hizo el de respaldo, sale el de respaldo.
- `fecha` está en UTC y es la de la generación: una respuesta de la caché conserva la suya.
- Es nulo en un resultado sin cobertura, donde no se llama al modelo.
- Lo generado es el texto que redacta el modelo. El aviso y las secciones «Cobertura del
  análisis», «Saneado de la salida» y «Verificación de citas» las añade el código.

`saneado` y `generado_por_ia` son campos nuevos y opcionales en los dos esquemas (OpenAPI y
`outputSchema`), así que un cliente que valida con el esquema anterior sigue funcionando.
Pendiente: fijar el formato definitivo con el código de buenas prácticas del art. 50.7
(decisión D-4 de la revisión), decidir si hace falta además una cabecera HTTP y mostrar en la
web el aviso de que el informe lo genera una IA (art. 50.1).

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
cada cliente y anotar qué revisión negocia cada uno.

## Modo stdio (servidor local)

Para los clientes que lanzan el servidor como un proceso suyo y le hablan por su entrada y su
salida estándar (RF-22: «y por stdio en local»). Es el mismo servidor que `/mcp`:
`app/mcp_stdio.py` llama a `build_mcp_server` (mismas herramientas, esquemas, textos y capa
de servicio) sobre el índice y el modelo que carga `app.main.load_engine`, la función que
usa también el `lifespan` de la API. La orden, desde cualquier directorio:

```
uv run --directory <ruta del repositorio> python -m app.mcp_stdio
```

o `make mcp-stdio` desde el repositorio. `--directory` hace falta porque el cliente lanza el
proceso desde el directorio de su proyecto, y `.env` y `CHROMA_DB_PATH=./chroma_db` se buscan
en el directorio de trabajo. Requisitos: el índice construido (`make ingest`) y
`GROQ_API_KEY` en el `.env` del repositorio. Con una clave de Groq no válida,
`listar_normativas` y `consultar_obligaciones` funcionan igual (no llaman al modelo) y
`analizar_proyecto` devuelve `MODELO_NO_DISPONIBLE`.

En Claude Code (ámbito local, fuera del repositorio):
`claude mcp add legaldev -- uv run --directory <ruta del repositorio> python -m app.mcp_stdio`
(sintaxis comprobada con `claude mcp add --help` de la versión 2.1.268: sin `--transport` es
stdio, y el ámbito por defecto es el local). En un fichero de configuración, el servidor es
`"command": "uv"` con
`"args": ["run", "--directory", "<ruta del repositorio>", "python", "-m", "app.mcp_stdio"]`
y sin `url` ni cabeceras. No se ha registrado todavía en ningún asistente real; la prueba de
abajo usa el cliente del SDK.

Qué cambia respecto a `/mcp`:

- **Sin clave, sin `Origin` y sin límites** (ni el cupo por minuto ni el tope diario). El
  proceso es hijo del cliente, corre en la máquina de quien lo lanza y gasta su propia clave
  de Groq; quien puede lanzarlo ya puede leer ese `.env`. Tampoco pasa por `McpGuard`: el
  tope de 256 KiB y el rechazo de lotes y claves repetidas existen en HTTP para que la guarda
  y el SDK lean lo mismo, y aquí solo lee el SDK.
- **stdout es del protocolo.** Los registros van a stderr, que los clientes guardan en su
  registro. El motor se carga dentro de `stdio_server()` del SDK, que mientras sirve desvía
  el descriptor 1 a stderr: lo que escriben las bibliotecas al cargar (barras de progreso,
  avisos) no llega al cliente. La carga va en un hilo y la primera petición del cliente espera
  en la tubería hasta que termina. El SDK no ofrece otra forma de abrir el transporte antes
  de cargar el motor que `MCPServer._lowlevel_server.run` (API privada, versión fijada, como
  `_tool_manager` en `_register`).
- **Las dos eras, como por HTTP:** la primera petición decide (`server/discover` de la
  2026-07-28 o `initialize` de la 2025-11-25).
- **PP-08 se mantiene:** el registro no contiene ni la descripción libre ni el `contexto`.

**Decisión: servidor local, no puente.** RF-22 admitía las dos formas. Se elige el servidor
local porque:

- RF-22, la precondición de CU-07 y el riesgo de latencia de 05-metodologia («ejecución local
  por stdio») ya lo suponían. 22-arquitectura («Despliegue») y 30-manual-instalacion
  describían un puente y se alinean con esta decisión (ver «Cambios que necesita la memoria»).
- Reutiliza `build_mcp_server` y el motor sin código de protocolo nuevo. Un puente propio
  tendría que reenviar las dos eras, el progreso, la cancelación y los errores, que es lo que
  ya hacen los puentes genéricos.
- No depende del Space (que se duerme) ni reparte claves de `/mcp`: cada desarrollador usa su
  propia clave de Groq, y `listar_normativas` y `consultar_obligaciones` ni siquiera la
  necesitan.

El precio es instalar las dependencias del repositorio (torch en CPU incluido), construir el
índice y esperar el arranque. Quien no quiera eso tiene el servidor remoto por HTTP, que
admiten los tres clientes de `clients/`. Para un cliente que solo hable stdio y quiera el
remoto existen puentes genéricos (por ejemplo, `mcp-remote`), que no se han probado con
LegalDev.

**Comprobado el 12/11/2026** con el cliente del SDK por stdio, con el índice real (22
documentos) y la orden de arriba lanzada desde otro directorio, en las dos eras (`mode="auto"`
negocia 2026-07-28 por `server/discover`; `mode="legacy"`, 2025-11-25 por `initialize`). En
el portátil de desarrollo (Windows, CPU), la primera respuesta llegó a los 71-73 s: casi todo
es importar las bibliotecas (solo `import app.main` tarda 44 s en esa máquina) y cargar los
dos modelos. Después, `listar_normativas` tardó 1,2-1,7 s, `consultar_obligaciones` (RGPD, 6
fragmentos) 6,6-11,4 s, y una normativa desconocida devolvió `NORMATIVA_DESCONOCIDA`. Todo lo
que escribieron las bibliotecas (peticiones a Hugging Face, barras de progreso) salió por
stderr. No se llamó a `analizar_proyecto`, para no gastar cuota de Groq: su camino es el
mismo que por HTTP (`service.analyze`) y la prueba automática lo cubre con el modelo simulado.
Son llamadas sueltas en una sola máquina, no una medición de latencia (RNF-19 sigue
pendiente), y no se comparan con los tiempos por HTTP de arriba: el motor es el mismo.
Ese arranque supera la espera por defecto de Claude Code: en la versión 2.1.268, la variable
de entorno `MCP_TIMEOUT` (en milisegundos) vale 30 000 si no se fija, así que para el modo
stdio hay que subirla, por ejemplo `MCP_TIMEOUT=120000` al lanzar `claude` (no probado
todavía con el asistente).

Pruebas en `tests/test_mcp_stdio.py`: lanzan el servidor como proceso hijo
(`tests/_mcp_stdio_launcher.py`, con el motor simulado, sin red y en un directorio sin
`.env`) y le hablan con el cliente del SDK, una sesión por era, con `tools/list` y una
llamada a cada herramienta. Los embeddings simulados escriben en stdout al cargarse: la sesión
funciona y ese texto aparece en stderr, junto con los registros, sin la descripción ni el
`contexto` aunque el nivel sea DEBUG. El código del proceso hijo no cuenta en la cobertura.

## Despliegue en el Space de Hugging Face

El Space (`https://gustavintavo8-legaldev.hf.space`) se despliega con `make push-space` desde
`main` (activado el 06/11/2026 con `main@a80c8b1`). Para activar el servidor MCP, en *Settings → Variables and secrets*: `MCP_ENABLED` =
`true` y `MCP_API_KEYS` con las claves que se repartan (secreto); `API_KEYS` sigue vacía para
la web. Los asistentes se conectan a `https://gustavintavo8-legaldev.hf.space/mcp` con la
cabecera `X-API-Key` (ejemplos en `clients/`). El cupo de `analizar_proyecto` es por clave y
comparte la cuota de Groq con la web. `MCP_DAILY_LIMIT` (variable, no secreto) añade el tope
diario por clave; en el Space todavía no está fijado.

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

## Tercera prueba con Claude Code, contra el Space (06/11/2026)

Cuestionario: ingeniero colegiado (persona física) de Andalucía, aplicación web de acceso
público con modelo freemium, usuarios registrados en la UE (sin menores), nombre y email,
cookies, IA generativa de un proveedor externo y datos a terceros. El asistente preguntó los
datos que faltaban, hizo 9 llamadas a LegalDev y marcó con la página del corpus cada punto que
salía de él, separándolo de lo que aportaba por su cuenta. Lo que señaló:

- **Normativas detectadas que el informe no desarrolla** (se repite de la segunda prueba): el
  RGPD y la EU AI Act estaban en `normativas_detectadas`, pero el informe no les dedicaba
  sección y el asistente tuvo que consultarlas con `consultar_obligaciones`. Depende del modelo
  y del prompt (decisión D-1), así que no se corrige ahí: una comprobación en código
  (`citations.normativas_sin_desarrollar`) las señala. Una normativa detectada cuenta como
  desarrollada si el informe tiene un encabezado con su nombre (comparando solo letras y
  dígitos) o una cita verificada en sus propios fragmentos; las demás salen las primeras en
  «Cobertura del análisis» y en `structuredContent.normativas_sin_desarrollar`, para que el
  asistente sepa qué tiene que consultar aparte.
- **Puntos del informe descartados por no venir al caso**: el consentimiento para descargar
  software de la LSSI (se refiere a los programas de marcación), la exportación de datos no
  personales del art. 12 ter (no son los datos de los usuarios), los datos WHOIS para las
  autoridades y mencionar el modelo freemium en el banner de cookies (la guía no lo pide).
  Evidencia para PI8: la recuperación trae fragmentos de la norma correcta que no aplican al
  caso, y el modelo los convierte en obligaciones.

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
  flexible. PP-02 comprueba que esquema y herramienta dan el mismo veredicto en 13 casos.
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
  (inalcanzable con RNF-15). El «tope diario por clave» del modelo de amenazas es
  `MCP_DAILY_LIMIT` desde el 12/11/2026 (ver «Tope diario por clave»).
- **Cupo de `consultar_obligaciones`.** No se limita (RNF-21 solo limita lo que consume cuota
  del modelo), pero ocupa unos 4 s de CPU por llamada. Con la clave obligatoria el riesgo es
  bajo; si hiciera falta, un cupo propio más amplio o un semáforo alrededor de la recuperación.
- **stdio.** Aplazado en la prueba de concepto; desde el 12/11/2026, servidor completo en
  local (`app/mcp_stdio.py`; ver «Modo stdio»).
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
- RF-22, precondición de CU-07, 22-arquitectura («Despliegue») y 30-manual-instalacion: el
  modo stdio es el servidor completo en local, no un puente; orden
  `uv run --directory <repositorio> python -m app.mcp_stdio`, sin clave ni límites, registros
  por stderr y unos 70 s de arranque en el portátil de desarrollo. Sale PT2-stdio de la tabla
  de pendientes del capítulo de resultados (`docs/tfg/requisitos.md` y
  `docs/tfg/trazabilidad.md` ya lo recogen).
- 23-detalle: `app.main.load_engine` carga el motor para el `lifespan` y para stdio;
  módulo nuevo `app/mcp_stdio.py`, que aún no figura en la tabla de módulos de
  `docs/tfg/modulos.md` (es la de `832ac33`).
- RNF-21 y modelo de amenazas (consumo de la cuota del modelo): tope diario por clave
  (`MCP_DAILY_LIMIT`), con qué cuenta y por qué (incluidos los aciertos de caché), su ventana
  de 24 h y su 429 con `Retry-After`; 30-manual-instalacion: la variable y su formato.
- RNF-20 pasa a implementado y sale de la tabla de pendientes (PT2-rnf20). Hay que contar qué
  retira el saneado, que se sanea antes de verificar las citas y la medición de identidad
  sobre los 13.756 fragmentos. También las tres decisiones: las URL de los fragmentos se
  respetan, `consultar_obligaciones` no se sanea y las órdenes en lenguaje natural no se
  cubren. Afecta al modelo de amenazas (inyección indirecta), a 22-arquitectura (paso
  nuevo del pipeline) y a 23-detalle (módulo `app/sanitize.py`, que tampoco está en la
  tabla de `docs/tfg/modulos.md`).
- PP-18 en 24-pruebas y en el capítulo de resultados: la prueba automática (17 cargas, en la
  descripción y en un fragmento, con un oráculo independiente) y la medición con el modelo
  real (ver «PP-18 con el modelo real»).
- tab:det-mcp-herramientas y 31-manual-usuario: campos nuevos `saneado` y `generado_por_ia`
  del resultado de `analizar_proyecto`, sección «Saneado de la salida» del informe, y el
  texto nuevo de las instrucciones del servidor y del aviso de los resultados MCP.
- «Cumplimiento del propio LegalDev» (Reglamento de IA, C-05): el marcado legible por
  máquina del art. 50.2 está en la API y en MCP (`generado_por_ia`); faltan el formato
  definitivo (D-4, código de buenas prácticas del art. 50.7) y el aviso en la web (art.
  50.1).

Siguen abiertas, como estaban: tipificación de las guías de la AEPD sin articulado y forma de
`sin_mapeo` en la evidencia (OE2).

## Acción de integración continua

TODO(PT6/RF-28): repositorio aparte `legaldev-action` (opcional; se decide el 1 de marzo de
2027). Consumirá `POST /v1/analyze` y `POST /v1/evidence`; sus pruebas PP-11 y PP-12 viven
en ese repositorio, no en este.
