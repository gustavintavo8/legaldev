# Uso de herramientas de IA en el desarrollo

> Procede de la declaración de originalidad de la memoria del TFG (etiqueta `pre-recorte-2026-11` del repositorio de la memoria, `capitulos/00-declaracion.tex` y su comentario de origen). La declaración conserva en un párrafo las herramientas, las tareas y la forma de verificar el resultado. Aquí queda el detalle de qué modelo figura en cada commit. Recuentos hechos el 9 de noviembre de 2026 sobre las revisiones que se indican en cada apartado.

La herramienta fue Claude Code, el agente de programación de Anthropic, con modelos Claude. Cada commit asistido registra el modelo en una línea `Co-Authored-By: Claude <modelo> <noreply@anthropic.com>`. Las líneas `Claude-Session: https://claude.ai/code/...` de algunos commits identifican además la herramienta. Los modelos que forman parte del propio LegalDev (`openai/gpt-oss-120b` y su respaldo) no se cuentan aquí; su elección se justifica en el capítulo de alternativas de la memoria y en [decisiones-prototipo.md](decisiones-prototipo.md).

## Cómo se reproduce

```bash
# Commits con alguna línea de coautoría de Claude
git log <revisión> -i --grep="Co-Authored-By: Claude" --format=%h | wc -l
# Commits que nombran un modelo concreto, con su fecha
git log <revisión> -i --grep="Co-Authored-By: Claude Sonnet 4.6" --format='%h %ad' --date=short
# Menciones por modelo (un commit fusionado por squash puede llevar varias)
git log <revisión> --format=%B | grep -i 'co-authored-by: claude' | sed 's/ <.*//' | sort | uniq -c
```

Un commit puede nombrar más de un modelo, así que la suma por modelo puede superar el número de commits con coautoría.

## legaldev hasta el punto de partida (`main@9f173ce`, 12 de septiembre de 2026)

Llevan coautoría de Claude 61 de los 159 commits de la rama principal. Es la cifra que da la declaración de la memoria.

| Modelo | Commits | Fechas |
|---|---|---|
| Claude Sonnet 4.6 | 56 | 9 de mayo a 24 de junio de 2026 |
| Claude Haiku 4.5 | 1 | 11 de mayo de 2026 |
| Claude Sonnet 5 | 2 | 11 y 12 de septiembre de 2026 |
| Claude Fable 5.1 | 4 | 11 y 12 de septiembre de 2026 |

La suma es 63 porque `eb6a880` y `d58db19` nombran a la vez Claude Sonnet 5 y Claude Fable 5.1. La revisión de código de mayo se hizo con un modelo Claude Opus. El commit que aplicó sus correcciones, `f185893` (10 de mayo, «fix: 4 issues from Opus review»), lleva la línea de Claude Sonnet 4.6.

Commits por modelo:

- **Claude Sonnet 4.6.**
  - 9 de mayo: `40d29b8`, `54fd09a`, `6276737`, `65a4af1`, `708dbed`, `80dd181`, `847db56`, `91a785f`, `9f91747`, `b7e7650`, `d7871e1`, `edbda17`.
  - 10 de mayo: `0232fc5`, `234d6f5`, `6646f4b`, `6d8ab69`, `8213817`, `84415ea`, `9236d4c`, `926ea45`, `a3ba4d8`, `d66482d`, `f185893`.
  - 11 de mayo: `599864e`, `69d6314`, `db7b09b`.
  - 15 de mayo: `1c0c00c`, `2f41eab`, `394071d`, `3acc7be`, `56887bb`, `5b8f83f`, `6fee068`, `d9103f4`, `eebeff9`.
  - 21 a 25 de mayo: `25d32f9`, `e4d1769`, `7294b69`, `0dc2d42`, `4734902`, `6c8d439`, `086cc97`, `321f362`, `6151bb1`, `87ca656`, `b0776b2`, `c1358d6`, `3ea006d`, `a99dbdf`, `b3671a5`, `dbce32b`.
  - Junio: `1f724d9`, `67fb319`, `6b85460` (14 de junio), `c3ca811`, `e254fd4` (24 de junio).
- **Claude Haiku 4.5.** `d4d13ca` (11 de mayo).
- **Claude Sonnet 5.** `eb6a880` (11 de septiembre), `d58db19` (12 de septiembre).
- **Claude Fable 5.1.** `eb6a880` (11 de septiembre), `07f7f3b`, `9f173ce`, `d58db19` (12 de septiembre).

## legaldev después del punto de partida (`9f173ce..832ac33`)

Son 25 commits, del 25 de septiembre al 6 de noviembre de 2026: andamiaje del TFG, correcciones de la revisión jurídica y servidor MCP. Llevan la línea de Claude Opus 5.5 todos menos las dos fusiones del 6 de noviembre, `c3d412d` y `e367f58`.

- 25 de septiembre: `026b5c3`, `8b46a2d`.
- 10 de octubre: `aa432e0`, `b597a08`, `c8d2d09`, `dc214fc`.
- 16 de octubre: `4cc1463`.
- 6 de noviembre: `1bcf0e8`, `2e63332`, `302b0b9`, `34c94fb`, `4dea740`, `5866b3f`, `593403e`, `601d010`, `70e7442`, `832ac33`, `83ea78b`, `a4951d8`, `a80c8b1`, `cf6b32d`, `e6f8944`, `ec827b4`.

El commit que añade esta carpeta es posterior a `832ac33` y no entra en el recuento.

## legaldev-web (rama `master`, `92b586f`)

Llevan coautoría de Claude 35 de los 54 commits de la rama.

| Modelo | Commits | Fechas |
|---|---|---|
| Claude Sonnet 4.6 | 13 | 9 a 21 de mayo de 2026 (página estática) |
| Claude Opus 5.5 | 22 | 30 de octubre a 6 de noviembre de 2026 (rediseño en React y correcciones) |

## Repositorio de la memoria (`legaldev-tfg`, etiqueta `pre-recorte-2026-11`)

Llevan coautoría 26 de los 28 commits. Los dos del 18 de septiembre de 2026 (`237a920` y `998a2f4`, especificación, datos y esqueleto LaTeX) no la llevan.

| Modelo | Commits | Fechas |
|---|---|---|
| Claude Fable 5.1 | 7 | 22 a 25 de septiembre de 2026 |
| Claude Opus 5.5 | 19 | 26 de septiembre a 9 de noviembre de 2026 |

- **Claude Fable 5.1.** 22 de septiembre: `8d6ffba` (primera redacción completa), `db4054d`, `2c61467`, `9624cb0`. 25 de septiembre: `0e7478c`, `89e79c8`, `1dfc3cd`.
- **Claude Opus 5.5.** 26 de septiembre: `cf5f3d9` (cinco documentos, recorte y corrección). 1 de octubre: `ee89494` (revisión de estilo), `e3804f0` (correcciones estructurales), `db125f1`, `ea25131`. 6 de noviembre: `115c062`, `3d0f8b8`, `3d172e9`, `41cb465`, `4642701`, `773031c`, `8c1c2c3`, `933e551`, `a7b0039`, `a8eaa73`, `b7a1453`, `cd19ea9`, `d5fcdf5`. 9 de noviembre: `5715a53`.

## Pendiente

- **ADM-modelos.** Al depositar hay que repetir los recuentos sobre la etiqueta de depósito (`tfg-deposito-2027-06`) y sobre la revisión final de la memoria, y actualizar con ellos la declaración.
