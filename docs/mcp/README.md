# Servidor MCP de LegalDev

**Estado: propuesto.** No hay servidor MCP en ejecución: `app/mcp_server.py` es un esqueleto
que no se monta en la aplicación y `MCP_ENABLED` vale `false` y todavía no tiene efecto.
Requisitos RF-22 a RF-25, RNF-15, RNF-16 y RNF-18 a RNF-21; caso de uso CU-07; pruebas
PP-01 a PP-08 y PP-13 a PP-18; criterio CA-09; paquete de trabajo PT2.

## Diseño resumido

- Punto de entrada `/mcp` en la misma aplicación FastAPI, con transporte Streamable HTTP de la
  revisión **2026-07-28** de la especificación, escrito con el SDK oficial de Python (línea
  2.x; la versión la fija la prueba de concepto de PT2). Comparte proceso, caché y claves de
  API con la API REST a través de la capa de servicio común (`app/service.py`).
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
los 12 primeros hexadecimales del MD5 de su texto (`service.fragment_id`); el artículo, el
número como cadena; la página, en base 1.

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

Compatibilidad con la revisión 2025-11-25: decisión abierta (21-analisis). Un cliente de esa
revisión empieza por `initialize` sin las cabeceras nuevas y recibe 400; el mensaje debe
nombrar las versiones soportadas. Si los clientes de la demostración siguen en 2025-11-25,
hará falta un servidor de doble era.

## Seguridad

`app/mcp_guard.py`, en el orden de 22-arquitectura («Flujo sin estado de una invocación»,
paso 3), antes de despachar el JSON-RPC:

1. `Origin` (RNF-18): 403 si viene y no está en una lista propia de `/mcp`, independiente de
   CORS (PP-16).
2. Cabeceras (RNF-16): 400 con `HeaderMismatch` (PP-14).
3. Versión (RNF-16): 400 con `UnsupportedProtocolVersionError` y las soportadas (PP-01).
4. Clave de API (RNF-15): siempre obligatoria; 401 sin clave, 403 con una desconocida. Sin
   `API_KEYS` la ruta no se monta (PP-07).
5. Límite (RNF-21): solo `tools/call` de `analizar_proyecto`, la única herramienta que consume
   cuota del modelo; por clave de API y, si no la hay, por IP; 429 (PP-17).

Además: descripciones de herramientas y del campo `descripcion_breve` estáticas y fijadas por
una prueba de instantánea (RNF-15); registros sin la descripción libre ni el `contexto`
(PP-08); salida saneada, sin reproducir la descripción ni órdenes al asistente (RNF-20,
PP-18); progreso por etapas y cancelación al cerrar el flujo SSE (RNF-19); etiqueta `via`
(`rest`, `mcp` o `ci`) en métricas y registros.

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

En local, la URL es `http://localhost:8000/mcp`. La comprobación se hace con el modo de línea
de órdenes de MCP Inspector (`npx @modelcontextprotocol/inspector --cli --method tools/list
--transport http --server-url <URL>/mcp --header "X-API-Key: $LEGALDEV_API_KEY"`), que debe
listar las tres herramientas.

TODO(PT2/CU-07): comprobar el registro de `/mcp` en VS Code, Cursor, Claude Code y MCP
Inspector con la versión vigente de cada cliente y, sobre todo, qué revisión de MCP hablan;
completar con el puente `stdio` para los clientes que solo lo admiten.

## Diferencias con la memoria

Comprobado contra la memoria recortada del 25/09/2026. Ya no queda ninguna diferencia por la
inicialización: RF-22, RNF-16, PP-01, PI6, CA-09, CU-07 y 22-arquitectura describen el flujo
sin `initialize`, y PP-01 es ahora «Versión y capacidades en cada petición» (PP-13 cubre
`server/discover`).

Quedan decisiones que la memoria deja abiertas o describe de forma incoherente entre
capítulos; el esqueleto sigue la opción indicada y deja el TODO correspondiente:

- **Orden de las comprobaciones de `/mcp`.** 22-arquitectura y CU-07 comprueban origen,
  cabeceras, versión, clave y límite; 23-detalle pone un middleware anterior al SDK con
  `Origin`, clave y límite, y las cabeceras después. Se sigue 22-arquitectura.
- **Clave del límite.** RNF-21, 22-arquitectura y 23-detalle dicen «por clave e IP»;
  `tab:ana-errores-mcp`, «por clave o, si no la hay, por IP». Se sigue esta última (con la
  clave obligatoria, equivale a por clave). El «tope diario por clave» del modelo de
  amenazas está sin concretar.
- **`consultar_obligaciones`.** RF-25, 22-arquitectura y 23-detalle la definen sin LLM
  (fragmentos con su localización); la tabla de herramientas de 31-manual-usuario («con citas
  verificadas»), el objetivo y el flujo 3a de CU-07 («obligaciones de una normativa») y el
  orden de recorte de 05-metodologia («en una versión determinista sin LLM») describen aún
  la variante que redacta obligaciones. Se sigue RF-25.
- **Esquema de `analizar_proyecto`.** 22-arquitectura y 23-detalle publican la dependencia
  `usa_ia` -> `tipo_ia` con `if`/`then`; la tercera precisión de 20-requisitos dice que el
  esquema publicado no la expresa. Se sigue 22/23; el servidor revalida siempre con Pydantic.
- **stdio.** 22-arquitectura y 30-manual-instalacion prevén un puente local hacia el servidor
  remoto; RF-22, la precondición de CU-07 y el riesgo de latencia de 05-metodologia suponen
  el servidor ejecutándose en local. Sin decidir (`run_stdio`).
- **Guías de la AEPD sin articulado.** La memoria propone tipificarlas por sección o por un
  vocabulario controlado; el andamiaje proponía páginas. Sin decidir: hasta entonces quedan
  «sin tipificar».
- **Forma de `sin_mapeo` en la evidencia.** `lst:det-evidencia` solo la muestra vacía; el
  esquema toma normativa, artículo y cita de `lst:det-alg-tipificacion`.

TODO(PT2/RNF-16): trasladar a la memoria lo que decida la prueba de concepto de PT2.

## Acción de integración continua

TODO(PT6/RF-28): repositorio aparte `legaldev-action` (opcional; se decide el 1 de marzo de
2027). Consumirá `POST /v1/analyze` y `POST /v1/evidence`; sus pruebas PP-11 y PP-12 viven
en ese repositorio, no en este.
