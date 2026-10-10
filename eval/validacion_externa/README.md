# Validación externa (PT7)

> Estado: sin iniciar. TODO(PT7/CA-08): seleccionar los informes, acordar el protocolo con la
> persona revisora, recoger las dos valoraciones y calcular el acuerdo.

Protocolo de la memoria (capítulo de pruebas, «Protocolo de validación externa»; criterio de
aceptación CA-08):

- Entre 15 y 20 informes del sistema híbrido S sobre el conjunto de prueba y, para 8 a 10 de
  sus cuestionarios, los informes de B1: la comparación con B1 forma parte del protocolo, no
  es opcional.
- Valoración ciega: antes de la revisión se quitan las secciones «Cobertura del análisis» y
  «Verificación de citas», que delatan la configuración; los informes se presentan en orden
  aleatorio y con un identificador aleatorio, y la tabla que relaciona identificador, caso y
  configuración se guarda aparte y no se comparte hasta terminar.
- Una persona con formación jurídica en derecho digital valora cada obligación en los dos ejes
  de `eval/annotation_guide.md` (jurídico y de respaldo).
- El autor valora los mismos informes de forma independiente; se calcula la kappa de Cohen
  por eje, ponderada en el de respaldo, que es ordinal (`eval/metrics.py`).
- La muestra del mapeo (adecuado, parcial, inadecuado) la valora otra persona, con perfil de
  SGSI (implantación o auditoría de ISO/IEC 27001), no la revisora jurídica.
- Si no hay revisión jurídica, la memoria lo hará constar y presentará solo la valoración del
  autor con esa limitación explícita.

## Datos personales

Este directorio no contiene datos identificativos de la persona revisora: figura con un
seudónimo, «revisor A», y un perfil genérico (p. ej. «formación jurídica en derecho
digital»). No se guardan aquí su nombre, su contacto ni su firma. Sus valoraciones son datos
seudonimizados (art. 4.5 RGPD), que siguen siendo datos personales para el autor, que conserva
fuera del repositorio la correspondencia y el consentimiento (arts. 6.1.a y 7.1 RGPD).
Los informes valorados solo contienen cuestionarios del conjunto de prueba, sin datos
personales.

## Ficheros previstos

- `muestra.csv`: identificador aleatorio y obligación (sin configuración).
- `valoraciones_autor.csv` y `valoraciones_revisor_a.csv`: identificador, eje jurídico, eje
  de respaldo y comentario (incluida la adecuación de la acción técnica).
- `valoraciones_mapeo_revisor_b.csv`: identificador de la obligación, control o medida,
  adecuación y comentario (perfil de SGSI).
- `correspondencia.csv`: identificador -> caso y configuración; se añade al repositorio solo
  cuando ambas valoraciones están cerradas.

TODO(PT7/CA-08): fijar las columnas definitivas y la hoja de instrucciones para la persona
revisora.
