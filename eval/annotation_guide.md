# Guía de anotación del conjunto acotado (esqueleto)

> Estado: borrador de estructura. TODO(PT4): redactar los criterios de cada apartado, probarlos
> con 5 casos piloto y fijar la guía (con fecha) antes de anotar el resto.

Base en la memoria: capítulo de pruebas, «Ampliación del gold standard», «Métricas» y
«Protocolo de validación externa» (escala `tab:pru-escala`). Alcance: RGPD, LOPDGDD, LSSI y la
guía de cookies de la AEPD.

## 1. Principios

- Se anota el caso a partir del cuestionario, sin ver ninguna salida del sistema (ni de S ni
  de las líneas base).
- Cada decisión lleva una justificación breve que remite al artículo o apartado.
- Ante la duda, `dudosa` con la razón; no se fuerza un `si` o un `no`.

## 2. Nivel de normativa

Por cada una de las cuatro fuentes: `si` | `no` | `dudosa`, con justificación.

TODO(PT4): criterios de aplicabilidad por fuente (ámbito material y territorial del RGPD,
LOPDGDD como desarrollo en España, noción de servicio de la sociedad de la información de la
LSSI, uso de cookies o tecnologías similares para la guía) y lista de casos límite con su
decisión. Ejemplo de caso dudoso ya identificado en la memoria: el DSA en plataformas cerradas
(fuera del alcance anotado, pero la guía debe decir cómo tratarlo si aparece).

## 3. Nivel de fragmento

Para cada fuente que aplica: artículos (o apartados y páginas, en la guía de cookies, que no
tiene articulado) que un informe correcto debería apoyar. Sirven para el MRR y la proporción
de fragmentos pertinentes.

TODO(PT4): regla para artículos largos partidos en varios fragmentos y para considerandos.

## 4. Nivel de obligación: escala de dos ejes

La pregunta PI3 tiene dos condiciones (obligación **respaldada por el texto citado** y
**jurídicamente correcta**), así que cada obligación se valora en dos ejes independientes:

**Eje J, jurídico** (¿la obligación es cierta y aplica a este proyecto?)

| Valor | Criterio |
|---|---|
| J3 | Correcta y accionable: aplica, el sujeto obligado es el correcto y la implementación propuesta es adecuada. |
| J2 | Correcta, implementación mejorable: aplica; la acción técnica es incompleta o imprecisa. |
| J1 | Sobreaplicada: la obligación existe pero no aplica al proyecto tal como se describe. |
| J0 | Incorrecta: no existe, atribuye el sujeto equivocado o contradice la norma. |

**Eje R, respaldo de la cita** (¿el texto citado justifica la obligación?)

| Valor | Criterio |
|---|---|
| R2 | La cita respalda la obligación por sí sola. |
| R1 | La cita es pertinente pero insuficiente (hace falta otro artículo o contexto). |
| R0 | La cita no la respalda o no existe en la norma (lo juzga la persona, no el verificador automático). |

**Correspondencia con la escala 1-5 de la memoria (`tab:pru-escala`)**, para informar los
resultados en el formato previsto: J0 → 1; si no, R0 → 2; si no, J1 → 3; J2 → 4; J3 → 5.

TODO(PT4): decidir cómo cuenta R1 en la escala 1-5 (propuesta: como R2, e informar R1 aparte) y
ajustar la memoria: hoy define una sola escala que mezcla los dos ejes.

## 5. Adecuación del control asignado (submuestra, PI5)

`adecuado` | `parcial` | `inadecuado`, con justificación, para el control o la medida que el
mapeo asigna a la obligación.

TODO(PT7/CA-08): criterios de adecuación compartidos con la persona revisora.

## 6. Registro

Las anotaciones viven en los YAML de `eval/cases/acotado/` (ver su README) y se congelan con
su hash antes de la primera ejecución.
