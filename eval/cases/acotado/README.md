# Conjunto de prueba acotado

> Estado: vacío. TODO(PT4): generar el núcleo combinatorio, redactar los 40-60 casos y
> anotarlos según `eval/annotation_guide.md`.

Diseño en la memoria: capítulo de pruebas, «Conjuntos de desarrollo y de prueba» (factores
del núcleo combinatorio en `tab:pru-estratos`). Es el conjunto de prueba; el de desarrollo es
la batería de regresión de `tools/eval_cases.yaml` (13 casos de `make eval`), que se mantiene
tal cual y no se mezcla con este.

## Alcance

- Entre 40 y 60 casos nuevos en cuatro bloques: un núcleo combinatorio por pares
  (*pairwise*) sobre los factores de `tab:pru-estratos`, generado con PICT con la restricción
  de que el tipo de IA solo existe si hay IA; 10-15 casos adversos a las reglas (la semántica
  del campo y la aplicabilidad divergen); casos fuera de dominio y límite (dominios lejanos,
  descripciones ambiguas, inyección de instrucciones); y 5-10 proyectos reales con
  repositorio público, que sirven también para PI7.
- Se anotan solo cuatro fuentes: **RGPD, LOPDGDD, LSSI y la guía de cookies de la AEPD**. Las
  demás normativas que recupere el sistema no cuentan ni como acierto ni como falso positivo.
- Salvo los proyectos reales, que remiten a un repositorio público, las descripciones son
  ficticias. Ningún caso contiene datos personales.

## Formato previsto

Un fichero YAML por caso, `NNN-<slug>.yaml`, con el cuestionario completo (sin `overrides`
sobre una base común, para que cada caso se lea y se congele por sí solo):

```yaml
id: acotado-001
bloque: nucleo                  # nucleo | adverso | fuera_de_dominio | real
factores:                       # niveles de tab:pru-estratos (núcleo combinatorio)
  tipo_proyecto: ecommerce
  datos_personales: identificativos
  cookies_acceso_publico: cookies-publico
fuera_de_dominio: false
cuestionario:                   # QuestionnaireInput completo; se valida con el modelo
  tipo_proyecto: ecommerce
  descripcion_breve: "Tienda online de ..."
  # ... los 16 campos
anotacion:
  normativas:
    RGPD:
      aplica: si                # si | no | dudosa
      justificacion: "..."
      fragmentos:               # solo si aplica: artículos o apartados pertinentes
        - articulo: 6
        - articulo: 13
    LOPDGDD: { aplica: si, justificacion: "...", fragmentos: [] }
    LSSI: { aplica: dudosa, justificacion: "..." }
    "Guía sobre uso de cookies - AEPD":
      aplica: si
      justificacion: "..."
      fragmentos:
        - paginas: [<n>]        # la guía no tiene articulado; páginas en base 1
notas: "..."
```

TODO(PT4): fijar el formato definitivo con un validador (Pydantic) antes de redactar el
primer caso, y decidir cómo se identifica un fragmento para el MRR (artículo o página frente a
hash de contenido, que no sobrevive a un reindexado).

## Regla de congelación

1. La anotación se hace **antes** de ver ninguna salida del sistema para ese caso.
2. Antes de la **primera ejecución** de `eval/run.py` el conjunto y la guía de anotación se
   congelan (la memoria publica su hash): se calcula el
   SHA-256 del contenido canónico de los casos (cada YAML parseado y volcado como JSON con
   claves ordenadas, UTF-8, en orden de nombre de fichero; así no influyen los comentarios ni
   los finales de línea que cambia `core.autocrlf` en Windows) y se guarda en
   `FROZEN.sha256` junto con la fecha, en un commit propio.
3. `eval/run.py` recalcula el hash, aborta si no coincide y lo escribe en cada resultado.
4. Cualquier cambio posterior (una errata incluida) crea un conjunto nuevo (`acotado-v2/`) y
   obliga a repetir todas las ejecuciones; los resultados de versiones distintas no se mezclan.

TODO(PT4): congelar el conjunto (el cálculo del hash está pendiente en `eval.run.verify_frozen`).
