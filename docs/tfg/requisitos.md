# Requisitos: texto completo

> Procede de los capítulos de requisitos y de análisis de la memoria del TFG (etiqueta `pre-recorte-2026-11` del repositorio de la memoria, `capitulos/20-requisitos.tex` y `capitulos/21-analisis.tex`). Los Documentos técnicos de la memoria conservan una línea por requisito, con su prioridad, su verificación, su objetivo y su estado. Aquí está el enunciado completo de las historias de usuario, de los requisitos funcionales y no funcionales y de los criterios de aceptación, y el detalle de los casos de uso de operación. Los requisitos del prototipo se comprueban en `main@9f173ce`; los del servidor MCP, en `832ac33`.

Los requisitos siguen ISO/IEC/IEEE 29148. Los no funcionales se ordenan por las características de calidad de ISO/IEC 25010. Los valores de diseño (umbrales, tamaños de contexto, reglas y tiempos límite) están en el código y en el capítulo de diseño de los Documentos técnicos. La relación de cada requisito con sus casos de uso, sus pruebas y sus criterios está en [trazabilidad.md](trazabilidad.md).

## Historias de usuario

Siguen la plantilla «como … quiero … para …». HU-10 a HU-12 motivan las aportaciones del TFG.

| Id | Historia | Requisitos |
|---|---|---|
| HU-01 | Como desarrollador, quiero describir mi proyecto en un formulario breve de opciones cerradas para saber qué normativas le aplican sin conocer la terminología jurídica. | RF-01 a RF-03, RF-21 |
| HU-02 | Como desarrollador, quiero que cada obligación traiga la cita literal con la norma y la página para contrastarla con la fuente oficial antes de actuar. | RF-08, RF-09 |
| HU-03 | Como desarrollador, quiero acciones técnicas concretas por obligación para llevarlas a mi lista de tareas. | RF-08 |
| HU-04 | Como desarrollador, quiero saber qué normativas del corpus no se han considerado para no darme por cubierto frente a ellas. | RF-11 |
| HU-05 | Como desarrollador, quiero saber cuántas citas se han verificado para calibrar la confianza que merece el informe. | RF-10 |
| HU-06 | Como integrador, quiero una API REST documentada, con respuestas JSON y errores explícitos, para incorporar el análisis a mis herramientas. | RF-01, RF-12, RF-13, RF-15 a RF-17 |
| HU-07 | Como mantenedor, quiero reconstruir el índice con un comando y saber qué versión del corpus sirve producción para actualizar las normas sin dejar el servicio sin índice. | RF-18, RF-20 |
| HU-08 | Como mantenedor, quiero detectar si el modelo de lenguaje sigue disponible y recurrir a uno de respaldo para que su retirada no deje el servicio fallando sin aviso. | RF-13, RF-19, RF-20 |
| HU-09 | Como usuario de la API, quiero valorar un informe concreto para dar al mantenedor una señal con la que mejorar el sistema. | RF-14 |
| HU-10 | Como desarrollador que trabaja con un asistente de programación, quiero preguntarle desde mi entorno qué normativa aplica y qué obligaciones impone, con la respuesta y las citas verificadas de LegalDev, para no depender de lo que el asistente recuerde de las normas. | RF-22 a RF-25 |
| HU-11 | Como responsable de seguridad, quiero que cada obligación se traduzca a controles de ISO/IEC 27001 o medidas del ENS con una evidencia exportable que me sirva para justificar la declaración de aplicabilidad del SGSI sin rehacer el análisis. | RF-26, RF-27 |
| HU-12 | Como integrador, quiero que la integración continua falle cuando el proyecto declare un tratamiento sin las medidas asociadas para comprobar el cumplimiento en cada cambio. | RF-28 |

HU-08 procede de un incidente real. Groq retiró el modelo en uso el 17 de julio de 2026 y la API de producción devolvió 503 en todos los análisis hasta que se detectó, el 11 de septiembre.

## Requisitos funcionales

Cada enunciado se lee precedido de «el sistema deberá». RF-01 a RF-21 corresponden al prototipo y RF-22 a RF-28, a las aportaciones del TFG. Las tablas se agrupan por capacidad.

- **Pr. (prioridad, MoSCoW):** M (*must*, imprescindible), S (*should*, importante con alternativa), C (*could*, deseable y recortable) y W (*won't*, excluido de esta versión).
- **Ver. (verificación):** P (prueba automatizada), I (inspección), D (demostración) y A (análisis o medición).
- **CU:** caso de uso en el que participa.
- **Estado:** Impl. (implementado), Parcial (implementado en parte) o Prop. (propuesto).

### Análisis del proyecto (punto de partida)

| Id | Requisito | Pr. | Ver. | CU | Estado |
|---|---|---|---|---|---|
| RF-01 | **Envío del cuestionario.** Aceptar en `POST /v1/analyze` un cuestionario JSON de 16 campos que describe el proyecto (tipo, datos personales, menores, IA, cookies, monetización y comunidad autónoma, entre otros). | M | P | 01 | Impl. |
| RF-02 | **Validación de la entrada.** Validar cada petición antes de procesarla (enumeraciones cerradas, longitud máxima de la descripción, tipo de IA obligatorio si se declara IA) y rechazar la inválida con HTTP 422 y el detalle del error. | M | P | 01 | Impl. |
| RF-03 | **Construcción de la consulta.** Traducir el cuestionario a una consulta en lenguaje natural que añade términos jurídicos por cada campo activo. | M | P | 01 | Impl. |
| RF-04 | **Recuperación.** Recuperar del índice los fragmentos que superan un umbral de relevancia, con búsquedas auxiliares condicionadas por el cuestionario, y responder 404 si no queda ninguno. | M | P, A | 01 | Impl. |
| RF-05 | **Exclusiones.** Descartar con reglas deterministas los fragmentos de las normativas que el cuestionario indica como no pertinentes; el ENS se excluye siempre como norma aplicable. | M | P | 01 | Impl. |
| RF-06 | **Inyecciones.** Garantizar en el contexto las normativas que el cuestionario indica como pertinentes (por ejemplo, el RGPD si hay datos personales), salvo que estén excluidas. | M | P, A | 01 | Impl. |
| RF-07 | **Reordenación y selección.** Reordenar los candidatos con un modelo *cross-encoder* y seleccionar el contexto con un tope de fragmentos por normativa. | S | P, A | 01 | Impl. |
| RF-08 | **Generación del informe.** Generar con el modelo de lenguaje un informe de estructura fija: sumario, una sección por normativa y, por obligación, cita, interpretación y acciones técnicas. | M | I, D | 01 | Impl. |
| RF-09 | **Citas textuales.** Exigir al modelo que cada obligación se apoye en una cita literal de un fragmento recuperado, con la normativa y la página. | M | P, I | 01 | Impl. |
| RF-10 | **Verificación de citas.** Comprobar en código, de forma determinista, si cada cita aparece literalmente en los fragmentos recuperados e informar del resultado sin modificar ni bloquear el informe. | M | P | 01 | Impl. |
| RF-11 | **Cobertura.** Enumerar al final del informe las normativas indexadas de las que no se recuperó ningún fragmento y, desde el 6 de noviembre de 2026, en otras dos listas, las detectadas que el informe no desarrolla y las que solo aportaron uno. | S | P | 01 | Impl. |

### Integración en el flujo de desarrollo mediante MCP (OE1)

| Id | Requisito | Pr. | Ver. | CU | Estado |
|---|---|---|---|---|---|
| RF-22 | **Servidor MCP.** Exponer un servidor MCP conforme a la revisión 2026-07-28 por HTTP transmitible en `/mcp` (y por stdio, como puente al servidor remoto o como servidor en local) que implemente `server/discover` y atienda `tools/list` y `tools/call` sin negociación inicial ni sesiones. RNF-16 detalla la conformidad y la compatibilidad con los clientes de la 2025-11-25. | M | P, D | 07 | Impl. |
| RF-23 | **Herramienta `analizar_proyecto`.** Recibir el cuestionario con las validaciones de RF-02 y devolver el informe como texto. Como contenido estructurado, devolver de nuevo el informe, el cuestionario validado (con los valores por defecto y sin la descripción libre), las normativas detectadas y las que el informe no desarrolla, los fragmentos con su identificador y su localización, el modelo, la versión del corpus, las estadísticas de citas, el aviso y si faltó cobertura. Una entrada inválida produce un error de herramienta (`isError`), no del protocolo, que enumera todos los campos que fallan. | M | P | 07, 08 | Impl. |
| RF-24 | **Herramienta `listar_normativas`.** Devolver, sin argumentos, los documentos indexados y la versión del corpus, leídos del índice como en RF-12. | S | P | 07 | Impl. |
| RF-25 | **Herramienta `consultar_obligaciones`.** Dada una normativa y un contexto breve, devolver sin llamar al modelo de lenguaje los fragmentos más pertinentes de esa normativa con su localización; una normativa desconocida produce un error de herramienta con la lista de las disponibles. | C | P | 07 | Impl. |

> **Decidido (PT2-stdio, 12 de noviembre de 2026).** El modo stdio de RF-22 es el servidor completo en local (`uv run --directory <repositorio> python -m app.mcp_stdio`), no un puente al servidor remoto: mismas herramientas y mismo motor, sin clave ni límites y con los registros por stderr. Razones y mediciones en [`docs/mcp/README.md`](../mcp/README.md), «Modo stdio».

### Mapeo a controles y evidencias (OE2)

| Id | Requisito | Pr. | Ver. | CU | Estado |
|---|---|---|---|---|---|
| RF-26 | **Mapeo a controles.** Asociar cada obligación tipificada (normativa, artículo o sección de origen y fragmento que respalda la cita) a controles del Anexo A de ISO/IEC 27001:2022 y medidas del Anexo II del ENS mediante una tabla versionada con justificación por entrada, aplicada en código y no por el modelo de lenguaje. | M | P, I | 07–09 | Prop. |
| RF-27 | **Evidencias exportables.** Generar a partir del análisis de un cuestionario una evidencia en JSON, validable contra su esquema, y en Markdown, con las versiones del corpus y del mapeo y, por obligación, la cita y su verificación, los controles y medidas, la acción y un estado que rellena el equipo; disponible en `POST /v1/evidence` y en el resultado de `analizar_proyecto`. | M | P | 07–09 | Prop. |

### Comprobación en integración continua (OE3, opcional)

| Id | Requisito | Pr. | Ver. | CU | Estado |
|---|---|---|---|---|---|
| RF-28 | **Acción de CI.** Ofrecer una acción de GitHub que lea una declaración `legaldev.yml` (cuestionario y medidas declaradas), obtenga la evidencia y termine con fallo si se incumple una regla de bloqueo, sin leer el código fuente. | C | P, D | 09 | Prop. |

### Acceso, operación y mantenimiento (punto de partida)

| Id | Requisito | Pr. | Ver. | CU | Estado |
|---|---|---|---|---|---|
| RF-12 | **Normativas indexadas.** Devolver en `GET /normativas` los documentos presentes en el índice, leídos del propio índice. | S | P | 02 | Impl. |
| RF-13 | **Estado del servicio.** Exponer el estado en `/health` y, en `/health/deep`, una comprobación con llamadas reales al índice y al proveedor del modelo. | S | P | 03, 06 | Impl. |
| RF-14 | **Valoración.** Registrar en `POST /v1/feedback` la valoración voluntaria (de 1 a 5, con comentario opcional) de un informe identificado por su petición. | C | P | 04 | Impl. |
| RF-15 | **Caché.** Servir desde una caché en memoria con caducidad la respuesta a un cuestionario idéntico e indicarlo en la cabecera `X-Cache`. | S | P | 01, 07 | Impl. |
| RF-16 | **Límite de peticiones.** Limitar por IP las peticiones de análisis y de valoración y responder 429 al superar el límite. | M | P | 01, 04, 07 | Impl. |
| RF-17 | **Claves de API.** Si se configura una lista de claves, exigir `X-API-Key` en el análisis: 401 sin clave y 403 con una clave desconocida. | S | P | 01, 07 | Impl. |
| RF-18 | **Reindexado del corpus.** Reconstruir el índice con un comando: comprobar los documentos requeridos, segmentar por artículo registrando el de cada fragmento que pertenezca a uno y sustituir el índice anterior solo cuando el nuevo esté completo. | M | P, A | 05 | Parcial |
| RF-19 | **Respaldo del modelo.** Reintentar con un modelo de respaldo si falla el principal, responder 503 si fallan ambos y declarar en cada respuesta qué modelo la generó. | S | P | 01, 03 | Impl. |
| RF-20 | **Guardia de arranque.** Negarse a arrancar con un índice vacío o construido con otro modelo de embeddings y comprobar al arrancar que el modelo de lenguaje sigue disponible. | S | P | 03, 05, 06 | Impl. |
| RF-21 | **Interfaz web.** Ofrecer una web estática con controles cerrados para un subconjunto del cuestionario que envíe la petición y muestre el informe o el error. | S | D | 01, 03, 06 | Impl. |

### Fuera de esta versión (W)

Leer el código fuente del repositorio; pedir al anfitrión que redacte el informe mediante muestreo (*sampling*), obsoleto en la revisión 2026-07-28; publicar las normativas como *resources* o plantillas como *prompts*; tratar el ENS como norma aplicable. Se justifica en los capítulos de alternativas y de diseño de la memoria.

### Aclaraciones

- **RF-04 a RF-07 son etapas de un mismo proceso** y su orden importa: exclusiones antes del recorte, reordenación sobre todos los candidatos e inyecciones al final.
- **RF-09 y RF-10 son distintos a propósito.** RF-09 impone un formato al modelo y RF-10 lo comprueba en código, porque el modelo puede incumplir el formato sin avisar.
- **RF-18 está implementado en parte.** El metadato de artículo solo llega al 10,3 % de los fragmentos (1.422 de 13.756, medido el 25 de septiembre de 2026). RF-09 no se ve afectado, porque el formato de cita exige la normativa y la página, no el artículo. RF-26 sí lo necesita, junto con el fragmento que respalda cada cita, que RF-10 no localiza. Las dos carencias se corrigen en el paquete PT10, anterior a PT3.
- **RF-22 a RF-25 usan el motor a través de una capa de servicio común** (`app/service.py`), con la que `POST /v1/analyze` y `analizar_proyecto` comparten una sola entrada de caché por cuestionario. El esquema de entrada no es idéntico por construcción: el que genera Pydantic no expresa la regla «tipo de IA obligatorio si se declara IA». El esquema publicado la expresa con `if`/`then`, y la herramienta revalida siempre con el modelo Pydantic en modo estricto. PP-02 comprueba que esquema y herramienta dan el mismo veredicto sobre cuestionarios válidos e inválidos.
- **El ENS tiene doble papel.** Se excluye como norma aplicable (RF-05) y se usa como catálogo de medidas en RF-26.
- **RF-21 expone solo parte del cuestionario** y fija el resto de campos, mientras que la API admite el cuestionario completo (detalle en [modulos.md](modulos.md), apartado del frontend).

## Requisitos no funcionales

Se agrupan por característica de calidad de ISO/IEC 25010 en su edición de 2011. ISO la anuló en marzo de 2024, tras publicar la segunda edición en noviembre de 2023.

> **Pendiente (C-37).** Migrar a la edición de 2023 de ISO/IEC 25010 o justificar el uso de la de 2011.

Llevan las mismas claves de prioridad, verificación y estado que los funcionales. Los del servidor MCP (RNF-15, RNF-16 y RNF-18 a RNF-21) responden a obligaciones de la revisión 2026-07-28, a los tiempos de espera de los clientes y a las amenazas propias de un servidor remoto: peticiones desde orígenes no autorizados, inyección indirecta a través de la salida de las herramientas y consumo de la cuota del proveedor del modelo.

### Eficiencia de desempeño

| Id | Requisito y métrica | Pr. | Ver. | Estado |
|---|---|---|---|---|
| RNF-01 | **Tiempo de respuesta.** La recuperación y la llamada al modelo tienen tiempos máximos configurables: agotado el de la recuperación se responde 503, y el del modelo activa el respaldo (RF-19). Un análisis completo en producción respondió en 22,7 s el 18 de septiembre de 2026. | M | A, P | Impl. |
| RNF-12 | **Recursos.** El servicio arranca con la memoria del plan gratuito de Hugging Face Spaces. El `README.md` atribuye unos 500 MB al modelo de embeddings y advierte de que el arranque puede fallar con menos de 700 MB libres; son cifras anteriores al reordenador y no medidas. | S | A | Parcial |
| RNF-19 | **Latencia frente a tiempos de espera.** Si la petición trae `progressToken`, `analizar_proyecto` emite `notifications/progress` al empezar y cada 5 s hasta terminar, en el flujo SSE de la respuesta, con lo que el cliente puede reiniciar su tiempo de espera. Si el cliente cierra el flujo, el servidor cancela la petición, y la recuperación en curso, que no se puede interrumpir, termina en segundo plano. La latencia p95 por MCP en caliente es menor que el tiempo de espera por defecto de los clientes de la demostración. | M | P, A | Parcial |

> **Pendiente (PT2-memoria).** Medir la memoria residente del proceso con los dos modelos cargados (RNF-12).
>
> **Pendiente (PT2-latencia).** Medir la latencia p50 y p95 por MCP en el Space, en caliente y en frío, con una muestra (RNF-19).

### Fiabilidad

| Id | Requisito y métrica | Pr. | Ver. | Estado |
|---|---|---|---|---|
| RNF-02 | **Disponibilidad ante fallos del proveedor.** El servicio sigue respondiendo si falla el modelo principal (RF-19) y muestra el estado real del proveedor en `/health/deep` (RF-13). La comprobación es bajo demanda: no hay un aviso programado. | S | P | Parcial |
| RNF-07 | **Determinismo.** Para un mismo cuestionario e índice, la recuperación es determinista, el modelo se invoca con temperatura 0 y la verificación de citas es una función pura sin acceso a red. | M | P | Impl. |

> **Pendiente (PT2-monitor).** Flujo programado que consulte `/health/deep` y avise del fallo (RNF-02).

### Seguridad

| Id | Requisito y métrica | Pr. | Ver. | Estado |
|---|---|---|---|---|
| RNF-04 | **Privacidad de los registros.** Los registros no contienen la descripción del usuario, solo su longitud y un resumen *hash* de 8 caracteres (32 bits), que es un dato seudonimizado y no anónimo. El identificador de petición que acompaña a cada evento debe validarse. Hoy lo puede fijar el cliente en `X-Request-ID` sin ninguna validación. | M | P | Parcial |
| RNF-05 | **Inyección directa de instrucciones.** La descripción del usuario llega al modelo delimitada y declarada no fiable; los patrones conocidos de inyección se detectan y registran sin rechazar la petición. | M | P | Impl. |
| RNF-06 | **Control de acceso y abuso.** Límite por IP (RF-16), claves opcionales (RF-17) y CORS restringido a GET y POST, a las cabeceras necesarias y a los orígenes configurados. | M | P | Impl. |
| RNF-15 | **Acceso al servidor MCP.** `/mcp` exige siempre una clave de API válida en `X-API-Key`, responde 401 si falta y 403 si no es válida y no se monta sin claves. Puede tener un conjunto de claves propio (`MCP_API_KEYS`), para dejar sin clave la API REST que usa la web pública. Las descripciones de las herramientas son estáticas y los registros no contienen la descripción libre del proyecto ni el `contexto` de `consultar_obligaciones`. | M | P | Impl. |
| RNF-18 | **Validación del origen.** `/mcp` valida la cabecera `Origin` de cada petición contra `MCP_ALLOWED_ORIGINS` y responde 403 si está presente y no es válida, como exige la revisión frente al *DNS rebinding*. Es una lista propia, independiente de CORS y sin comodín. | M | P | Impl. |
| RNF-20 | **Salida segura.** El resultado de las herramientas es información para el desarrollador, no instrucciones para el agente: se sanea (caracteres de control, HTML y enlaces), no reproduce la descripción libre, separa cita, interpretación y acción, y no contiene órdenes dirigidas al asistente ni peticiones de invocar herramientas. Mitiga la inyección indirecta a través de la salida. | M | P, I | Prop. |
| RNF-21 | **Límite por invocación.** La revisión obliga a limitar la frecuencia de invocación de las herramientas. `/mcp` solo limita las llamadas `tools/call` a `analizar_proyecto`, la única herramienta que consume cuota del modelo, por clave de API y con el cupo y el almacén de la API REST. Al superarlo responde 429 con `Retry-After`. El método y la herramienta se leen del cuerpo, no de `Mcp-Name`, que no envían los clientes de la revisión anterior. No se limitan el descubrimiento, el listado ni las otras dos herramientas, que solo leen el índice local y también exigen la clave. Desde el 12 de noviembre de 2026, `MCP_DAILY_LIMIT` añade un tope diario por clave a esas llamadas, en el mismo almacén y después del cupo por minuto (vacío, sin tope). | S | P | Impl. |

> **Pendiente (PT2-rnf20).** Saneado de la salida del modelo (RNF-20) y prueba PP-18 con el modelo real.

### Compatibilidad

| Id | Requisito y métrica | Pr. | Ver. | Estado |
|---|---|---|---|---|
| RNF-16 | **Conformidad con MCP.** El servidor cumple el protocolo de la revisión 2026-07-28. Lee la versión y las capacidades del cliente del `_meta` de cada petición, rechaza una versión no soportada con `UnsupportedProtocolVersionError` y comprueba que las cabeceras `MCP-Protocol-Version`, `Mcp-Method` y `Mcp-Name` coinciden con el cuerpo. Incluye `resultType` en todos los resultados de esa revisión, `ttlMs` y `cacheScope` en los de `server/discover` y `tools/list`, y orden determinista en `tools/list`. Es un servidor de doble era: una petición sin `MCP-Protocol-Version`, o con una revisión anterior en ella, se atiende con la negociación inicial (`initialize`) de la 2025-11-25 y anteriores, también sin sesiones. En producción se ha probado con Claude Code y, en las dos eras, con el cliente del SDK. | M | P, D | Impl. |

> **Pendiente (PT2-clientes).** Registrar `/mcp` en VS Code y Cursor (y en MCP Inspector) y anotar qué revisión negocia cada uno y cómo presenta el 401 de la clave.

### Mantenibilidad

| Id | Requisito y métrica | Pr. | Ver. | Estado |
|---|---|---|---|---|
| RNF-08 | **Reproducibilidad del índice.** El índice registra el modelo de embeddings, la versión del corpus, el número de fragmentos y documentos y la versión del segmentador; la versión del corpus acompaña a cada respuesta. | M | P | Impl. |
| RNF-09 | **Calidad del código.** Suite de 420 pruebas automatizadas que pasan, con cobertura mínima del 80 % exigida en la integración continua (medida en local: 95 %), junto con análisis estático y comprobación de formato. | M | P | Impl. |
| RNF-10 | **Observabilidad.** Métricas Prometheus en `/metrics` y registros JSON con identificador de petición, devuelto en la cabecera `X-Request-ID`. | S | P | Impl. |
| RNF-17 | **Trazabilidad del mapeo.** Cada entrada cita el identificador exacto del control (por ejemplo, `A.5.34`) o de la medida (por ejemplo, `mp.info.1`) y su fuente; la tabla lleva versión y fecha, que se copian en cada evidencia junto con la versión del corpus. | M | P, I | Prop. |

### Portabilidad y operación

| Id | Requisito y métrica | Pr. | Ver. | Estado |
|---|---|---|---|---|
| RNF-03 | **Coste de operación nulo.** Inferencia, alojamiento de la API y de la web, y código y CI en planes gratuitos de Groq, Hugging Face Spaces, Vercel y GitHub. | S | I | Impl. |
| RNF-11 | **Portabilidad.** Imagen Docker con el índice y los dos modelos locales, sin descargas en producción (`HF_HUB_OFFLINE`); Python 3.11 o superior. | S | D | Impl. |

### Usabilidad

| Id | Requisito y métrica | Pr. | Ver. | Estado |
|---|---|---|---|---|
| RNF-13 | **Idioma.** Corpus, cuestionario, *prompt* e informe en español. | M | I | Impl. |
| RNF-14 | **Usabilidad de la web.** El formulario se adapta al móvil, indica si la API está en línea, avisa de que la primera consulta puede tardar más por el arranque en frío del servidor y muestra el carácter orientativo de la información. | C | D | Impl. |

## Restricción: dependencias externas de la web

Las demás restricciones del pliego (carácter informativo, fuentes oficiales, corpus estático, minimización de datos, propiedad intelectual y transparencia del método) se tratan en el capítulo de aspectos legales y éticos de la memoria. Esta solo estaba en el capítulo de requisitos, y se describía así en la revisión `0a1f03c` de `legaldev-web`, anterior al rediseño:

> La página carga tipografías de Google Fonts y la biblioteca `marked` desde un CDN, lo que transmite la IP del visitante a esos terceros. La biblioteca se carga sin versión fija ni integridad de subrecursos. La documentación de la API (`/docs`) carga también Swagger UI desde `cdn.jsdelivr.net` y su icono desde `fastapi.tiangolo.com`. No instala cookies propias ni usa analítica.

**Estado a 9 de noviembre de 2026.** La rama `master` de `legaldev-web` es, desde el 30 de octubre de 2026, una aplicación React. Fija `marked` en `package.json`, sirve las tipografías desde el propio sitio (`@fontsource`) y sanea el informe con DOMPurify (`src/lib/markdown.ts`). En la API no ha cambiado nada: `app/main.py` usa la documentación por defecto de FastAPI, que sigue cargando Swagger UI desde jsDelivr. Falta confirmar qué revisión de la web está publicada en Vercel (pendiente C-29, en [modulos.md](modulos.md)).

## Criterios de aceptación

| Id | Criterio | Requisitos |
|---|---|---|
| CA-01 | En cada uno de los 13 casos de la batería de regresión (conjunto de desarrollo), todas las normativas esperadas aparecen en el contexto recuperado y ninguna de las marcadas como no esperadas lo hace (falso positivo). | RF-04 a RF-07 |
| CA-02 | La suite automatizada pasa completa en la integración continua con una cobertura igual o superior al 80 %. | RNF-09 |
| CA-03 | Una petición válida a producción devuelve 200, en menos de 60 segundos, con un informe que contiene sumario, secciones por normativa, citas, la sección de cobertura y la de verificación de citas. | RF-01, RF-08 a RF-11, RNF-01 |
| CA-04 | Una petición con un valor fuera de las enumeraciones, una descripción de más de 500 caracteres o uso de IA sin tipo se rechaza con 422. | RF-02 |
| CA-05 | La petición de una misma IP que supera 10 peticiones por minuto en un punto de entrada limitado recibe 429; una petición repetida dentro de una hora recibe `X-Cache: HIT` sin invocar al modelo. | RF-15, RF-16 |
| CA-06 | Con un índice construido con otro modelo de embeddings el servicio no arranca; con el modelo principal indisponible, el análisis se sirve con el de respaldo y lo declara en `llm_model`. | RF-19, RF-20 |
| CA-07 | El reindexado con un documento ausente aborta antes de tocar el índice existente; el reindexado completo deja `.index_meta.json` y `.corpus_version` en el índice nuevo. | RF-18, RNF-08 |
| CA-08 | Una persona con formación jurídica valida la calidad de los informes (corrección de las obligaciones extraídas y de su interpretación) sobre una muestra de 15 a 20 informes, con el protocolo de validación externa. | RF-08, RF-09 |
| CA-09 | Vaciando la caché entre las dos vías y con el modelo de lenguaje simulado, para cada caso de la batería de regresión, `analizar_proyecto`, invocada por un cliente conforme a la revisión 2026-07-28, y `POST /v1/analyze` entregan al modelo los mismos fragmentos, en el mismo orden (comparados por su identificador), y devuelven las mismas normativas detectadas y la misma versión del corpus; `listar_normativas` devuelve los mismos documentos que `GET /normativas`. Además, `server/discover` anuncia la revisión y `tools/list` devuelve exactamente las tres herramientas, ambos con `ttlMs` y `cacheScope`; una versión no soportada recibe `UnsupportedProtocolVersionError` y un `Origin` no permitido recibe 403. | RF-22 a RF-25, RNF-16, RNF-18 |
| CA-10 | Sobre las obligaciones tipificadas del conjunto de prueba: todos los identificadores del mapeo existen en el catálogo y cada evidencia valida contra su esquema; como máximo el 30 % de las obligaciones queda como «sin control técnico aplicable», cada una con su justificación; y en una muestra revisada por una persona con perfil de SGSI (responsable de seguridad o auditor), al menos el 80 % de las entradas, incluidas las marcadas «sin control», se consideran adecuadas. | RF-26, RF-27, RNF-17 |
| CA-11 | En un repositorio de ejemplo cuyo `legaldev.yml` declara datos personales sin política de privacidad (indicador de que falta la información de los arts. 13 y 14 del RGPD), la acción termina con fallo y publica el motivo; con la política declarada, termina con éxito. | RF-28 |

CA-01 a CA-07 se refieren al punto de partida y CA-08 a CA-11, a las aportaciones del TFG.

- **CA-01 es una comprobación de regresión, no una evaluación.** Las reglas se ajustaron sobre esos mismos casos, así que no mide la generalización, que corresponde al conjunto de prueba de OE4.
- **CA-09 compara salidas deterministas.** El texto del informe depende del modelo de lenguaje, y la caché compartida haría trivial la igualdad.
- **Los umbrales de CA-10 se fijan antes de la primera ejecución** y no se ajustan a la vista de los resultados. El máximo de «sin control» impide cumplir el criterio marcando así todas las obligaciones, y la revisión externa impide cumplirlo con controles genéricos. La especificidad del mapeo se mide aparte.

## Casos de uso de operación

Los Documentos técnicos conservan el diagrama de casos de uso, la ficha compacta de CU-07 y dos líneas para CU-08 y CU-09. Aquí está el detalle de CU-01 y de los casos auxiliares del punto de partida. Los códigos HTTP y los valores numéricos son los que aplica el código en `main@9f173ce`.

### CU-01: Analizar proyecto

| Campo | Contenido |
|---|---|
| Actores | Desarrollador (web), integrador (API) y, con OE1, el asistente de programación a través de CU-07; proveedor del modelo de lenguaje. |
| Objetivo | Obtener un informe con la normativa aplicable al proyecto, con obligaciones, citas y acciones de implementación. |
| Precondiciones | El servicio está arrancado con un índice válido. Si hay claves de API configuradas, el integrador dispone de una. |
| Flujo principal | El actor envía el cuestionario (`POST /v1/analyze`; la web lo construye desde el formulario). El sistema asigna un identificador de petición o respeta el de `X-Request-ID`, aplica las comprobaciones previas, recupera y selecciona los fragmentos, genera el informe, verifica las citas y responde 200 con las normativas detectadas (dos o más fragmentos). |
| Flujos alternativos | Clave ausente: 401; inválida: 403. Cuestionario inválido: 422 con el detalle de los campos. Límite superado: 429. Respuesta en caché para un cuestionario idéntico: 200 con `X-Cache: HIT`. Recuperación de más de 60 s: 503. Ningún fragmento: 404. Falla el modelo principal: se reintenta con el de respaldo y se registra; fallan ambos: 503. Alguna cita no se localiza: se lista en «Verificación de citas» y el informe se sirve igualmente. |
| Postcondiciones | Respuesta en caché durante 3.600 s; métricas y registro sin datos personales. |
| Requisitos | RF-01 a RF-11, RF-15 a RF-17, RF-19, RF-21. |

Las comprobaciones baratas van antes que el trabajo costoso, en el orden que impone la implementación. La clave de API se comprueba como dependencia del punto de entrada, antes de validar el cuerpo. El limitador por IP envuelve al manejador y actúa después de la validación, y la caché se consulta ya dentro del manejador. Así, una petición inválida o repetida nunca carga la CPU con la reordenación ni consume cuota del proveedor del modelo.

La salida por falta de cobertura (404) solo se alcanza si no se activa ninguna inyección, porque las inyecciones no aplican umbral. Un cuestionario que declara datos personales o uso de IA recibe siempre un informe. Solo se quedan sin cobertura los proyectos que no activan ninguna regla y cuyo vocabulario está lejos del corpus.

### CU-02 a CU-06: casos auxiliares

El procedimiento de despliegue y el de reindexado, paso a paso, están en el [`README.md`](../../README.md) («Instalación» y «Deploy en Hugging Face Spaces») y en [`CONTRIBUTING.md`](../../CONTRIBUTING.md) («Re-indexing the corpus»).

| Caso, actores y requisitos | Disparador y resultado | Excepciones |
|---|---|---|
| CU-02 Consultar normativas. Desarrollador, integrador. RF-12 | `GET /normativas`: lista ordenada de los documentos del índice y su número (22). Sin clave ni límite. | Índice no disponible: lista vacía y total 0. |
| CU-03 Comprobar el estado. Monitorización, mantenedor; Groq. RF-13, RF-19 a RF-21, RNF-02, RNF-10 | `GET /health`: estado, fragmentos y versión del corpus. `GET /health/deep`: comprueba con llamadas reales índice y proveedor e informa de los modelos. También `/metrics` y `/`. | Sonda profunda de hace menos de 60 s: se reutiliza. Componente caído: campo con el tipo de excepción y HTTP 200. |
| CU-04 Valorar un informe. Integrador. RF-14, RF-16 | `POST /v1/feedback` con el identificador de petición, una puntuación de 1 a 5 y un comentario opcional: 201 y una línea en `feedback.jsonl`, el único dato que se persiste. | 429 por límite; 422 si el identificador no tiene de 1 a 64 caracteres `[A-Za-z0-9_-]` o el comentario supera 2.000. |
| CU-05 Reindexar el corpus. Mantenedor. RF-18, RF-20, RNF-08 | `make ingest`: índice nuevo en un directorio aparte, con versión y metadatos, intercambiado por el anterior. | Falta un documento: aborta sin tocar el índice. Intercambio fallido tras cinco intentos: restaura el anterior. |
| CU-06 Desplegar el servicio. Mantenedor; plataformas. RF-13, RF-20, RF-21, RNF-03, RNF-11 | `make push-space`: el Space construye la imagen y arranca tras la guardia de arranque; la web se despliega en Vercel. Se comprueba con `/health`. | Cambios sin confirmar o ficheros grandes fuera de LFS: aborta. Índice incompatible o vacío: no arranca. |
