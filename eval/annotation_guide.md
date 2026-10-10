# Guía de anotación del conjunto acotado (esqueleto)

> Estado: borrador de estructura. TODO(PT4): redactar los criterios de cada apartado, probarlos
> con 5 casos piloto y fijar la guía (con fecha) antes de anotar el resto.

Base en la memoria: capítulo de pruebas, «Conjuntos de desarrollo y de prueba», «Métricas y
escala de valoración» (escala de dos ejes, `tab:pru-escala`) y «Protocolo de validación
externa»; la guía congelada irá en el anexo de la memoria (`anexo:guia`). Alcance: tres
normas (RGPD, LOPDGDD y LSSI) y la guía de cookies de la AEPD, que es un criterio
interpretativo del art. 22.2 LSSI y no una norma.

## 1. Principios

- Se anota el caso a partir del cuestionario, sin ver ninguna salida del sistema (ni de S ni
  de las líneas base).
- Cada decisión lleva una justificación breve que remite al artículo o apartado.
- Ante la duda, `dudosa` con la razón; no se fuerza un `si` o un `no`.

## 2. Nivel de normativa

Por cada una de las cuatro fuentes: `si` | `no` | `dudosa`, con justificación.

TODO(PT4): criterios de aplicabilidad por fuente (ámbito material y territorial del RGPD;
LOPDGDD como norma que adapta el ordenamiento español al RGPD y completa sus disposiciones,
art. 1.a, y garantiza los derechos digitales, art. 1.b; noción de servicio de la sociedad de
la información de la LSSI; para la guía de cookies, criterio interpretativo del art. 22.2
LSSI y no norma, uso de cookies o tecnologías similares) y lista de casos límite con su
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

Los valores son los de `tab:pru-escala`:

**Eje jurídico** (¿la obligación es cierta y aplica a este proyecto?)

| Valor | Criterio |
|---|---|
| `correcta` | Aplica al proyecto descrito y recae sobre el sujeto correcto. |
| `sobreaplicada` | Existe, pero no aplica al proyecto tal como se describe (exceso de prudencia). |
| `sujeto_erroneo` | Existe, pero recae sobre otro sujeto (p. ej., el proveedor del modelo y no quien lo integra). |
| `incorrecta` | No existe o contradice la norma. |

**Eje de respaldo** (¿el texto citado justifica la obligación? Ordinal)

| Valor | Criterio |
|---|---|
| `respalda` | La cita contiene la obligación o su supuesto de hecho. |
| `parcial` | La cita es pertinente, pero la obligación exige más de lo que dice o se apoya solo en un considerando o en la exposición de motivos. |
| `no_respalda` | La cita no guarda relación con la obligación, aunque sea literal (lo juzga la persona, no el verificador automático). |

La adecuación de la acción técnica no es un eje: se anota como comentario.

## 5. Adecuación del control asignado (submuestra, PI5)

`adecuado` | `parcial` | `inadecuado`, con justificación, para el control o la medida que el
mapeo asigna a la obligación, incluidas las marcadas «sin control técnico aplicable». La
valora una persona con perfil de SGSI, no la revisora jurídica (CA-10: al menos el 80 %
adecuadas).

TODO(PT7/CA-10): criterios de adecuación compartidos con la persona revisora de perfil SGSI.

## 6. Registro

Las anotaciones viven en los YAML de `eval/cases/acotado/` (ver su README) y se congelan con
su hash antes de la primera ejecución.
