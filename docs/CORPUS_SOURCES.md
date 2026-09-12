# Fuentes del corpus

Los PDF de `docs/` no se versionan (`.gitignore`). Esta tabla documenta de dónde se descargó cada documento el 2026-09-12 para reconstruir el índice (`make ingest`). Si la fuente cambia de versión, cambia `corpus_version` (hash de nombre+tamaño) y conviene volver a pasar `make eval`.

| Documento | Fuente | Páginas | Bytes | SHA-256 (12) | Nota |
|---|---|---|---|---|---|
| Adecuación al RGPD de tratamientos que incorporan IA - AEPD.pdf | https://www.aepd.es/guias/adecuacion-rgpd-ia.pdf | 53 | 1697343 | `3a4343ca8f2d` |  |
| Cyber Resilience Act (Reglamento UE 2024-2847).pdf | https://eur-lex.europa.eu/legal-content/ES/TXT/PDF/?uri=CELEX:32024R2847 | 81 | 1829615 | `e219b1cf88fd` |  |
| Código Ético y Deontológico CCII.pdf | https://ccii.es/servicios/area-de-descargas?task=download.send&id=50:codigo-etico-y-deontologico-de-la-ingenieria-informatica&catid=12 | 17 | 623316 | `04a9b0af4d99` | Aprobado por la asamblea general del CCII el 4 de mayo de 2019; descarga vía el gestor jDownloads de ccii.es. |
| DORA (Reglamento UE 2022-2554).pdf | https://eur-lex.europa.eu/legal-content/ES/TXT/PDF/?uri=CELEX:32022R2554 | 79 | 1566969 | `e6e60fe523d5` |  |
| Data Act (Reglamento UE 2023-2854).pdf | https://eur-lex.europa.eu/legal-content/ES/TXT/PDF/?uri=CELEX:32023R2854 | 71 | 1463578 | `08b01d21ae0f` |  |
| Data Governance Act (Reglamento UE 2022-868).pdf | https://eur-lex.europa.eu/legal-content/ES/TXT/PDF/?uri=CELEX:32022R0868 | 44 | 1062727 | `763d9ffffe9e` |  |
| Digital Services Act (Reglamento UE 2022-2065).pdf | https://eur-lex.europa.eu/legal-content/ES/TXT/PDF/?uri=CELEX:32022R2065 | 102 | 1743243 | `73baf5a1983c` |  |
| Directiva NIS2.pdf | https://eur-lex.europa.eu/legal-content/ES/TXT/PDF/?uri=CELEX:32022L2555 | 73 | 1382029 | `798b7edb6046` |  |
| Directiva de Responsabilidad por Productos con IA.pdf | https://eur-lex.europa.eu/legal-content/ES/TXT/PDF/?uri=CELEX:32024L2853 | 22 | 1171152 | `e6d99e307e9b` | Directiva (UE) 2024/2853 sobre responsabilidad por los daños causados por productos defectuosos (incluye software y sistemas de IA). Sustituye a la propuesta de Directiva de responsabilidad en materia de IA (COM(2022) 496), retirada por la Comisión en 2025. |
| Directiva ePrivacy (2002-58-CE consolidada).pdf | https://eur-lex.europa.eu/legal-content/ES/TXT/PDF/?uri=CELEX:02002L0058-20091219 | 27 | 722618 | `aa3288595eb2` | Texto consolidado a 19/12/2009. |
| EU AI Act.pdf | https://eur-lex.europa.eu/legal-content/ES/TXT/PDF/?uri=CELEX:32024R1689 | 144 | 2679733 | `29e6d41f41cc` |  |
| Guía de Anonimización - AEPD.pdf | https://www.aepd.es/guias/guia-orientaciones-procedimientos-anonimizacion.pdf | 28 | 1310604 | `00fae40c93c3` |  |
| Guía de Análisis de Riesgos para tratamientos de datos personales - AEPD.pdf | https://www.aepd.es/guias/gestion-riesgo-y-evaluacion-impacto-en-tratamientos-datos-personales.pdf | 160 | 4638477 | `04eab6e9310b` | Corresponde a la guía «Gestión del riesgo y evaluación de impacto en tratamientos de datos personales» (junio 2021), que sustituye a la guía práctica de análisis de riesgos de 2018. |
| Guía de Privacidad desde el Diseño - AEPD.pdf | https://www.aepd.es/guias/guia-privacidad-desde-diseno.pdf | 58 | 1177659 | `0b9712b76b1a` |  |
| Guía para el cumplimiento del deber de informar - AEPD.pdf | https://www.aepd.es/guias/guia-modelo-clausula-informativa.pdf | 18 | 1701189 | `f4ac5c342f8d` |  |
| Guía sobre uso de cookies - AEPD.pdf | https://www.aepd.es/guias/guia-cookies.pdf | 40 | 1285192 | `f968645392c1` | Versión actualizada en mayo de 2024. |
| IA Agentica desde la perspectiva de proteccion de datos - AEPD.pdf | https://www.aepd.es/guias/orientaciones-ia-agentica.pdf | 76 | 2276116 | `ad33fd8f449c` | «Orientaciones sobre inteligencia artificial agéntica» de la AEPD (76 páginas). |
| LOPDGDD.pdf | https://www.boe.es/buscar/pdf/2018/BOE-A-2018-16673-consolidado.pdf | 68 | 542839 | `a736af56c1f5` | Texto consolidado del BOE. |
| LSSI.pdf | https://www.boe.es/buscar/pdf/2002/BOE-A-2002-13758-consolidado.pdf | 37 | 347950 | `b959ff69212d` | Texto consolidado del BOE. |
| Ley de Propiedad Intelectual.pdf | https://www.boe.es/buscar/pdf/1996/BOE-A-1996-8930-consolidado.pdf | 100 | 670420 | `42458597f9ea` | Texto consolidado del BOE. |
| RGPD.pdf | https://eur-lex.europa.eu/legal-content/ES/TXT/PDF/?uri=CELEX:32016R0679 | 88 | 1024768 | `a2fa3289de2f` |  |
| Real Decreto 311-2022 ENS.pdf | https://www.boe.es/buscar/pdf/2022/BOE-A-2022-7191-consolidado.pdf | 79 | 636205 | `07a74608dce3` | Texto consolidado del BOE. |
