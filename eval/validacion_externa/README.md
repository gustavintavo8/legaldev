# Validación externa (PT7)

> Estado: sin iniciar. TODO(PT7/CA-08): seleccionar los informes, acordar el protocolo con la
> persona revisora, recoger las dos valoraciones y calcular el acuerdo.

Protocolo de la memoria (capítulo de pruebas, «Protocolo de validación externa»; criterio de
aceptación CA-08):

- Entre 15 y 20 informes del sistema híbrido S sobre el conjunto acotado y, si la persona
  revisora lo acepta, un subconjunto de B1 para comparar.
- Valoración ciega: los informes se presentan con un identificador aleatorio; la tabla que
  relaciona identificador, caso y configuración se guarda aparte y no se comparte hasta
  terminar.
- Cada obligación se valora con la escala de `eval/annotation_guide.md` (dos ejes, con su
  correspondencia a la escala 1-5 de la memoria); en una submuestra, además, la adecuación del
  control o la medida asignados (adecuado, parcial, inadecuado).
- El autor valora los mismos informes de forma independiente; se calcula la kappa de Cohen
  ponderada (`eval/metrics.py`).
- Si no hay revisión jurídica, la memoria lo hará constar y presentará solo la valoración del
  autor con esa limitación explícita.

## Datos personales

Este directorio **no contiene datos personales**. No se guardan aquí el nombre, el contacto ni
la firma de la persona revisora, ni la correspondencia con ella: en el repositorio figura como
«revisor A» con su perfil profesional genérico (p. ej. «formación jurídica en derecho
digital»), y su consentimiento para citar esa descripción se conserva fuera del repositorio.
Los informes valorados solo contienen cuestionarios ficticios del conjunto acotado.

## Ficheros previstos

- `muestra.csv`: identificador aleatorio y obligación (sin configuración).
- `valoraciones_autor.csv` y `valoraciones_revisor_a.csv`: identificador, eje J, eje R,
  adecuación del control (si aplica) y comentario.
- `correspondencia.csv`: identificador -> caso y configuración; se añade al repositorio solo
  cuando ambas valoraciones están cerradas.

TODO(PT7/CA-08): fijar las columnas definitivas y la hoja de instrucciones para la persona
revisora.
