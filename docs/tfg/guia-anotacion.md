# Guía de anotación del conjunto de prueba (criterios de la memoria)

> Procede del anexo C de la memoria del TFG («Guía de anotación del conjunto de prueba», etiqueta `pre-recorte-2026-11` del repositorio de la memoria, `capitulos/40-anexos.tex`). Es el esqueleto de la guía con la que se anotará el conjunto de prueba de OE4 (paquete PT4). El diseño de la evaluación está en la memoria, en el apartado de OE4 del capítulo de resultados.

Dos ficheros de este repositorio completan la guía y no se repiten aquí:

- [`eval/annotation_guide.md`](../../eval/annotation_guide.md): principios, niveles de anotación, valores de la escala de dos ejes y adecuación del control asignado (PI5).
- [`eval/cases/acotado/README.md`](../../eval/cases/acotado/README.md): alcance del conjunto, formato YAML de cada caso y regla de congelación con su huella SHA-256.

Este documento añade lo que solo estaba en la memoria: los criterios de aplicabilidad por fuente, los criterios para decidir entre valores contiguos de la escala y un ejemplo resuelto.

> **Pendiente (OE4-guia).** Redactar la versión definitiva de la guía tras una anotación piloto (PT4). La tarea consta en la tabla de balance de pendientes del capítulo de resultados de la memoria.

## Qué se anota

La guía fija qué es correcto antes de ver ninguna salida del sistema. Así la referencia se construye desde la norma y no desde las reglas, al revés que en la batería de regresión (`tools/eval_cases.yaml`), cuyas expectativas se ajustaron junto con las reglas.

- **Caso.** Una descripción del proyecto y el cuestionario de referencia que se deduce de ella. En los proyectos reales la descripción es el repositorio, y el cuestionario anotado se usa también para PI7. Salvo indicación contraria, el responsable está establecido en España.
- **Fuentes.** Solo RGPD, LOPDGDD, LSSI y la guía de cookies de la AEPD. Las demás normativas que recupere el sistema no cuentan ni como acierto ni como error.
- **Niveles.** Normativa (aplica, no aplica o dudosa, con el precepto que lo decide) y fragmento (artículos o apartados pertinentes). En la guía de cookies, que no tiene rango normativo, esos valores indican si su criterio es pertinente.
- **Origen de la anotación.** Se anota desde la descripción, no desde los campos del cuestionario. Una aplicación móvil que guarda identificadores para analítica activa el art. 22.2 de la LSSI aunque declare `usa_cookies=false`.
- **Dudosas.** Se reservan a los hechos que la descripción deja sin determinar. Antes de congelar se reescribe la descripción. Las dudosas que queden se excluyen de las métricas principales y entran en un análisis de sensibilidad, primero como «aplica» y después como «no aplica».

> **Discrepancia por resolver.** `eval/annotation_guide.md` (apartado 1) dice que el caso se anota «a partir del cuestionario». La memoria fija lo contrario: se anota desde la descripción, porque el conjunto incluye casos adversos en los que el campo del cuestionario y la aplicabilidad divergen. Hay que alinear los dos documentos al redactar la versión definitiva (OE4-guia).

## Criterios de aplicabilidad por fuente

Comprobados en los textos del corpus.

| Fuente | Aplica (o es pertinente) cuando | Dudas previsibles y su resolución |
|---|---|---|
| RGPD | Se tratan datos personales (art. 4.1) en el contexto de un establecimiento en la Unión (art. 3.1) o, sin él, para ofrecer bienes o servicios a interesados que se encuentren en la Unión o controlar su comportamiento (art. 3.2, texto corregido). Basta un registro con correo electrónico. | Datos «ninguno» con usuarios registrados: aplica, porque la cuenta identifica a su titular. Uso exclusivamente personal o doméstico: no aplica (art. 2.2.c). |
| LOPDGDD | Aplica el RGPD a un tratamiento (art. 2.1) de un responsable establecido en España, criterio de anotación derivado del art. 3.1 del RGPD. | Usuarios menores: además, art. 7 si el tratamiento se basa en su consentimiento (propio desde los catorce años). |
| LSSI | Servicio de la sociedad de la información (a distancia, por vía electrónica, a petición del destinatario y a título oneroso, o gratuito si es actividad económica del prestador; anexo, letra a) de un prestador establecido en España (art. 2). El art. 10 no depende de las cookies. | Sin actividad económica (herramienta interna, proyecto personal): dudosa si la descripción no lo aclara. Contratación en línea: además, art. 27. |
| Guía de cookies | Se usan cookies u otros dispositivos de almacenamiento y recuperación de datos para finalidades no exceptuadas del art. 22.2 de la LSSI (analítica, publicidad comportamental, personalización no solicitada). | Solo cookies exceptuadas (técnicas, de sesión o de preferencias del usuario): no es pertinente, porque el art. 22.2 no les exige información ni consentimiento (la guía recomienda una mención genérica). Finalidad no descrita: dudosa. |

El art. 3.2 del RGPD se cita en su texto corregido («que se encuentren en la Unión»). El PDF indexado es el texto original, que dice «que residan» (`docs/CORPUS_SOURCES.md`).

## Criterios para decidir entre valores contiguos

Las salidas se valoran con la escala de dos ejes. El eje jurídico distingue entre correcta, sobreaplicada, sujeto erróneo e incorrecta, y el de respaldo de la cita, entre respalda, parcial y no respalda (definiciones en `eval/annotation_guide.md`, apartado 4). La calidad de la acción técnica propuesta se anota como comentario. Para los casos frontera:

| Duda | Criterio de decisión |
|---|---|
| Correcta o sobreaplicada | Si la obligación depende de un hecho que la descripción no afirma (entrenar un modelo, contratar en línea), es sobreaplicada. |
| Correcta o sujeto erróneo | Se identifica en el precepto quién está obligado (responsable o encargado; proveedor del modelo o quien lo integra) y qué papel tiene el proyecto (arts. 4.7 y 4.8 del RGPD). Si el informe atribuye al proyecto la obligación de otro, es sujeto erróneo. |
| Sobreaplicada o incorrecta | Es sobreaplicada si la obligación existe en la norma para otros supuestos, e incorrecta si no existe en ninguno o la contradice. |
| Respalda o parcial | Respalda si el fragmento contiene la obligación o su supuesto de hecho. Es parcial si la obligación exige más de lo que dice el fragmento o este es solo un considerando o la exposición de motivos. |
| Parcial o no respalda | No respalda si el fragmento trata de otra materia, aunque la cita sea literal y esté verificada. |

## Ejemplo resuelto: el informe real del 18 de septiembre de 2026

El caso es la plataforma SaaS para trabajadores autónomos de la consulta real a producción, reproducida en el apéndice A de los Documentos técnicos de la memoria.

**Aplicabilidad.** Aplican el RGPD (arts. 6, 13, 28, 30 y 32, y 44 a 49 si el proveedor del modelo trata datos fuera del EEE), la LOPDGDD (art. 11), que el informe real omite, y la LSSI (arts. 10 y 27). El art. 22.2 de la LSSI y la guía de cookies quedarían dudosos mientras la descripción no diga para qué se usan las cookies.

**Valoración de algunas obligaciones**, según la valoración del autor:

- Las garantías para las transferencias a terceros son correctas, pero su cita, una referencia al Reglamento 45/2001, no las respalda. La expresión mezcla la comunicación a un tercero (art. 4.10), el encargo (art. 28) y la transferencia fuera del EEE (cap. V).
- La intermediación de la LSSI está sobreaplicada, porque la caché de un SaaS no es la copia temporal del art. 15, y su respaldo es parcial.
- El resumen de los datos de entrenamiento tiene un sujeto erróneo: el art. 53.1.d) del Reglamento de IA obliga al proveedor del modelo.
- La clasificación como sistema de alto riesgo es incorrecta, y su cita, sobre usos en el empleo, no la respalda.

La valoración completa de las trece obligaciones está en el apéndice A de los Documentos técnicos.

## Procedimiento

1. El autor anota los casos antes de ejecutar ningún sistema.
2. Casos y guía se congelan con su huella SHA-256 antes de la primera ejecución, según la regla de `eval/cases/acotado/README.md`.
3. Las correcciones posteriores se registran como fe de erratas. `eval/cases/acotado/README.md` es más estricto: cualquier cambio, también una errata, crea un conjunto nuevo (`acotado-v2/`) y obliga a repetir las ejecuciones. Hay que dejar una sola regla en la versión definitiva (OE4-guia).
4. El revisor externo aplica la misma guía sin conocer la configuración que generó cada informe (protocolo en [`eval/validacion_externa/README.md`](../../eval/validacion_externa/README.md)).
