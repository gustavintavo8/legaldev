---
title: LegalDev
emoji: ⚖️
colorFrom: blue
colorTo: green
sdk: docker
app_port: 8000
short_description: RAG API de normativa legal para developers en España
pinned: false
---

# LegalDev

API RAG de normativa legal para developers en España. Describe tu proyecto de software y obtén las normativas europeas y españolas que te aplican, con implicaciones técnicas concretas.

> ⚠️ Esta herramienta es de orientación informativa y no constituye asesoramiento legal.

**Repositorio:** https://github.com/gustavintavo8/legaldev

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
