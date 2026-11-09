# Catálogo de detalle de la memoria del TFG

Esta carpeta acompaña a la memoria del Trabajo Fin de Grado «LegalDev: asistente de cumplimiento normativo para proyectos software integrado en el flujo de desarrollo mediante MCP» (Gustavo Sobrado Aller, Grado en Ingeniería Informática en Tecnologías de la Información, Escuela Politécnica de Ingeniería de Gijón, Universidad de Oviedo).

La memoria se redujo a unas cien páginas en noviembre de 2026. El detalle de catálogo que solo existía en ella, y que no hace falta para leerla, se trasladó aquí. Lo que ya estaba en el código o en otra documentación de este repositorio no se copia: cada fichero remite a su ruta.

## Ficheros

| Fichero | Contenido | Procede de (memoria, etiqueta `pre-recorte-2026-11`) |
|---|---|---|
| [requisitos.md](requisitos.md) | Texto completo de las historias de usuario, de los requisitos funcionales y no funcionales y de los criterios de aceptación; restricción sobre las dependencias externas de la web; casos de uso de operación (CU-01 a CU-06) | Requisitos (`20-requisitos.tex`) y análisis (`21-analisis.tex`) |
| [trazabilidad.md](trazabilidad.md) | Objetivos y sus requisitos; matriz requisito funcional → caso de uso → prueba → criterio de aceptación | Análisis (`21-analisis.tex`) y requisitos (`20-requisitos.tex`) |
| [casos-de-prueba.md](casos-de-prueba.md) | Dobles de prueba por nivel, `conftest.py`, suite por componente, casos CP-01 a CP-12, prueba de integración con índice real, desglose de las pruebas de citas y puntuaciones de la búsqueda | Pruebas (`24-pruebas.tex`) |
| [decisiones-prototipo.md](decisiones-prototipo.md) | Razonamiento de las decisiones del prototipo: embeddings y Railway, `normalize_embeddings`, reordenador fp32, cuota de Groq, entrada, segmentación, barrido del umbral de mayo, verificación de citas e infraestructura (`uv`, `ruff`, `slowapi`…) | Alternativas (`04-alternativas.tex`) |
| [modulos.md](modulos.md) | Módulos y dependencias, estructuras de datos, interfaces, pseudocódigo (selección diversa, segmentación y citas), ingesta, metadatos del índice, imagen Docker, métricas Prometheus y frontend, con aviso del rediseño en React | Diseño de detalle (`23-detalle.tex`) y arquitectura (`22-arquitectura.tex`) |
| [corpus.md](corpus.md) | Dónde están la URL, las páginas, los bytes y la huella de cada documento; totales por tipo; versión del corpus; notas que no recoge `docs/CORPUS_SOURCES.md` | Anexo A (`40-anexos.tex`) y análisis (`21-analisis.tex`) |
| [guia-anotacion.md](guia-anotacion.md) | Criterios de aplicabilidad por fuente, criterios para decidir entre valores contiguos de la escala de dos ejes y un ejemplo resuelto | Anexo C (`40-anexos.tex`) |
| [uso-ia.md](uso-ia.md) | Modelos de IA que figuran en los commits de cada repositorio, con sus commits y fechas | Declaración de originalidad (`00-declaracion.tex`) |

## Convenciones

- **Revisión de los datos.** Cada fichero dice al principio a qué revisión se refieren sus datos. `main@9f173ce` (12 de septiembre de 2026) es el punto de partida, el prototipo previo al TFG. `832ac33` (6 de noviembre de 2026) es la revisión con el servidor MCP.
- **Cifras.** Van escritas con su valor, tomado de `datos/cifras.tex` del repositorio de la memoria. Los ficheros de `datos/` que se citan (`pytest.txt`, `metadato_articulo.txt`…) están en ese repositorio, no en este.
- **Remisiones a la memoria.** Se hacen por documento y capítulo («capítulo de pruebas de los Documentos técnicos»), no por número de apartado, porque la numeración cambió con el recorte.
- **Pendientes.** Se marcan con el identificador de la tarea (por ejemplo, PT10-segmentador o C-29). La lista de tareas técnicas está en la tabla de balance del capítulo de resultados de la memoria, y las C-xx proceden de la revisión jurídica del 10 de octubre de 2026.

## Otra documentación del repositorio

| Tema | Dónde |
|---|---|
| Instalación, variables de entorno, API, despliegue, decisiones técnicas y limitaciones | [`README.md`](../../README.md) |
| Reglas de recuperación y reindexado del corpus | [`CONTRIBUTING.md`](../../CONTRIBUTING.md) |
| Fuentes del corpus y licencias | [`docs/CORPUS_SOURCES.md`](../CORPUS_SOURCES.md) y [`NOTICE.md`](../../NOTICE.md) |
| Servidor MCP: diseño, seguridad, clientes y pruebas con Claude Code | [`docs/mcp/README.md`](../mcp/README.md) |
| Conjunto de prueba, guía de anotación y validación externa (OE4) | [`eval/`](../../eval/) |
| Batería de regresión | [`tools/eval_cases.yaml`](../../tools/eval_cases.yaml) |
| Historial de cambios | [`CHANGELOG.md`](../../CHANGELOG.md) |
