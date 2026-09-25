# Servidor MCP de LegalDev

**Estado: propuesto.** No hay servidor MCP en ejecución: `app/mcp_server.py` es un esqueleto
que no se monta en la aplicación y `MCP_ENABLED` vale `false` y todavía no tiene efecto.
Requisitos RF-22 a RF-25, RNF-15 y RNF-16; caso de uso CU-07; pruebas PP-01 a PP-08; paquete
de trabajo PT2.

## Diseño resumido

- Punto de entrada `/mcp` en la misma aplicación FastAPI, con transporte Streamable HTTP de la
  revisión **2026-07-28** de la especificación. Comparte proceso, caché, límite por IP y
  claves de API con la API REST.
- Capa fina: las herramientas validan, delegan en el motor a través de `app/service.py` y
  traducen el resultado. No añaden lógica de recuperación ni de generación; la prueba de
  equivalencia PP-05 lo fija como invariante.
- Tres herramientas, en este orden:

| Herramienta | Requisito | Entrada | Resultado |
|---|---|---|---|
| `analizar_proyecto` | RF-23 | El cuestionario de `POST /v1/analyze` (esquema generado de `QuestionnaireInput`) | Informe en Markdown y contenido estructurado: normativas, fragmentos, modelo, versión del corpus, citas, controles (RF-26) y aviso |
| `listar_normativas` | RF-24 | Ninguna | Documentos indexados con tipo y nivel, y versión del corpus |
| `consultar_obligaciones` | RF-25 | `normativa`, `contexto` (máx. 500 caracteres) | Obligaciones de esa normativa con citas verificadas |

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
  lo usa: las herramientas reciben todos sus datos como argumentos.
- Sampling, Roots y Logging, obsoletos. LegalDev no los necesita: llama directamente a la API
  de Groq, que es la migración que recomienda la especificación para Sampling.

## Seguridad

`app/mcp_guard.py`: validación de `Origin` (403 si viene y no está permitido), clave de API
(401/403, como `/v1/analyze`), límite por IP solo en `tools/call` (429), descripciones de las
herramientas estáticas y fijadas por una prueba de instantánea, registros sin la descripción
libre ni el `contexto`, etiqueta `via=mcp` en métricas y registros.

## Configuración de clientes

Ejemplos en `clients/` con dos marcadores que hay que sustituir: `<URL>` (URL base del
servicio, sin barra final) y `<X-API-Key>` (solo si el servicio tiene `API_KEYS`). No escribas
la clave en un fichero que vaya a versionarse: VS Code admite `${input:...}` y Claude Code
expande variables de entorno `${VAR}` en `.mcp.json`.

- VS Code: `clients/vscode.mcp.json` -> `.vscode/mcp.json`
- Claude Code: `clients/claude-code.mcp.json` -> `.mcp.json`, o bien
  `claude mcp add --transport http legaldev <URL>/mcp --header "X-API-Key: <X-API-Key>"`
- Cursor: `clients/cursor.mcp.json` -> `.cursor/mcp.json`

TODO(PT2/CU-07): comprobar cada formato con la versión vigente de cada cliente y, sobre todo,
qué revisión de MCP hablan: si siguen en 2025-11-25, un servidor solo 2026-07-28 rechaza su
`initialize` y hace falta un servidor dual-era.

## Diferencias con la memoria

- RF-22, RNF-16, PP-01, CA-09 y el paso 1 de CU-07 (y el flujo de invocación de
  22-arquitectura) describen una «inicialización de la sesión» con `initialize`. La revisión
  2026-07-28 la elimina: su equivalente es `server/discover` y la versión en `_meta` de cada
  petición. PP-01 se implementará sobre `server/discover`.
- El límite por IP se aplica solo a `tools/call` (concreción de RNF-15).
- El mapeo admite una clave `paginas` para guías sin articulado (la memoria las deja «sin
  tipificar»), porque la guía de cookies es una de las cuatro fuentes del conjunto acotado.

TODO(PT2/RNF-16): trasladar estas diferencias a la memoria cuando el spike confirme el SDK.

## Acción de integración continua

TODO(PT6/RF-28): repositorio aparte `legaldev-action` (opcional; se decide el 1 de marzo de
2027). Consumirá `POST /v1/analyze` y `POST /v1/evidence`; sus pruebas PP-11 y PP-12 viven
en ese repositorio, no en este.
