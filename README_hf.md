---
title: LegalDev
emoji: ⚖️
colorFrom: blue
colorTo: green
sdk: docker
app_port: 8000
short_description: RAG API de normativa legal para developers en España
pinned: false
license: other
---

# LegalDev

API RAG de normativa legal para developers en España. Describe tu proyecto de software y obtén un informe orientativo sobre las normativas europeas y españolas que pueden aplicarte, con implicaciones técnicas concretas.

> ⚠️ Esta herramienta es de orientación informativa y no constituye asesoramiento legal. Cada informe incluye este aviso al principio y al final.

**Repositorio:** https://github.com/gustavintavo8/legaldev

**Privacidad.** No incluyas datos personales en la descripción del proyecto: el cuestionario se envía al proveedor del modelo (Groq), que según su política de datos puede conservarlo hasta 30 días en EE. UU. Esta API se aloja en Hugging Face, que registra la IP de cada petición. Qué datos se tratan y qué información falta por publicar: sección «Privacidad y datos» del README del repositorio.

**Licencias.** El código se publica con licencia MIT. El índice contiene fragmentos de guías de la AEPD (CC BY-NC-SA 4.0, solo uso no comercial) y de textos del BOE, de EUR-Lex y del CCII, cada uno con sus condiciones. Detalle en `NOTICE.md`.

## Uso rápido

```bash
curl -X POST https://<username>-legaldev.hf.space/v1/analyze \
  -H "Content-Type: application/json" \
  -d '{
    "tipo_proyecto": "app_web",
    "descripcion_breve": "Plataforma SaaS para gestión de contratos",
    "tiene_usuarios_registrados": true,
    "acceso_publico": false,
    "tipos_datos_personales": ["nombre", "email"],
    "usuarios_menores": false,
    "usuarios_ue": true,
    "transferencia_datos_terceros": false,
    "usa_ia": false,
    "tipo_ia": null,
    "usa_cookies": true,
    "monetizacion": "suscripcion",
    "contenido_digital": false,
    "ccaa": "Madrid",
    "es_empresa": true,
    "colegiado": null
  }'
```
