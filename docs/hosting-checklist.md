# LegalDev — Checklist para alojar en servidor propio

Documento para compartir con tu amigo antes de montar el hosting.

---

## Lo que corre

Una API HTTP en Python (FastAPI). Al arrancar:
- Carga un modelo de embeddings en RAM (~80 MB)
- Carga un reranker en RAM (~80 MB)
- Conecta a una base de datos vectorial local (ChromaDB, SQLite, sin servidor externo)
- Expone un puerto HTTP (por defecto 8000)

No hay base de datos externa, no hay Redis, no hay cola de mensajes. Todo en un solo proceso.

---

## Preguntas que hacerle a tu amigo

### 1. ¿Cuánta RAM libre tiene el servidor?

| RAM libre | ¿Funciona? |
|-----------|------------|
| < 1 GB | No |
| 1–2 GB | Con justa (puede matarlo el OOM killer bajo carga) |
| 2–4 GB | Bien para uso personal / demos |
| 4 GB+ | Cómodo |

**Pregunta:** "¿Cuánta RAM tiene el servidor en total y cuánto usa habitualmente el sistema?"

---

### 2. ¿Tiene Docker instalado?

**Opción A — Con Docker (recomendado):** Solo necesita ejecutar un comando. La imagen ya lleva los modelos descargados, Python y todo lo demás. No toca nada del sistema.

**Opción B — Sin Docker:** Necesita Python 3.11+ y uv instalados. Más pasos, más posibilidad de conflictos con otros proyectos que tenga en el servidor.

**Pregunta:** "¿Tienes Docker instalado? ¿Qué versión?"

```bash
docker --version
```

---

### 3. ¿El servidor tiene acceso a internet?

Necesario al menos la primera vez para:
- Descargar la imagen Docker (~600 MB) **o** instalar dependencias Python
- Los modelos ya van dentro de la imagen, no hace falta descarga adicional en runtime

Después del primer arranque, puede funcionar completamente offline.

**Pregunta:** "¿El servidor tiene salida a internet aunque sea para descargas iniciales?"

---

### 4. ¿Se puede exponer un puerto al exterior?

La API escucha en el puerto `8000` por defecto (configurable). Para que la frontend de Streamlit pueda llamarla desde fuera, ese puerto tiene que ser accesible.

Opciones, de más fácil a más robusto:

| Opción | Coste | Dificultad | Notas |
|--------|-------|------------|-------|
| **ngrok** (free tier) | Gratis | Muy fácil | URL pública temporal, cambia al reiniciar, límite de conexiones |
| **Cloudflare Tunnel** | Gratis | Fácil | URL estable, sin abrir puertos en el router, recomendado |
| **Puerto abierto en el router** | Gratis | Media | Necesita IP fija o DDNS; el amigo tiene que tocar el router |
| **Dominio propio + Nginx** | ~10€/año el dominio | Alta | Lo más profesional; sirve si el amigo ya lo usa |

**Pregunta:** "¿El servidor está detrás de un router doméstico o tiene IP pública directa? ¿Puedes instalar Cloudflare Tunnel?"

---

### 5. ¿Qué sistema operativo tiene?

La imagen Docker funciona en cualquier Linux (Ubuntu, Debian, Fedora, etc.) y en Windows Server con Docker Desktop. ARM (Raspberry Pi, Mac M-series) requeriría recompilar la imagen.

**Pregunta:** "¿Qué OS y arquitectura tiene el servidor?"

```bash
uname -m && cat /etc/os-release | head -3
```

Respuesta esperada: `x86_64` + Linux. Si sale `aarch64` hay que hablar.

---

### 6. ¿Cuánto espacio en disco tiene libre?

La imagen Docker ocupa ~700 MB. Los modelos van dentro. El `chroma_db` son ~50 MB.

**Mínimo necesario:** 2 GB libres.

**Pregunta:** "¿Cuánto espacio libre hay en disco?"

```bash
df -h /
```

---

## Resumen mínimo para que funcione

```
✅ RAM libre:     ≥ 2 GB (idealmente 4 GB)
✅ Docker:        instalado (versión 24+ recomendada)
✅ Internet:      solo para la primera descarga
✅ Puerto 8000:   accesible, via Cloudflare Tunnel o router
✅ OS:            Linux x86_64
✅ Disco:         ≥ 2 GB libres
```

---

## Lo que tú le mandas cuando esté listo

Una sola variable de entorno necesaria (la API key de Groq):

```bash
GROQ_API_KEY=gsk_xxxxxxxxxxxxxxxxxxxx
```

Y el comando para arrancar (una vez que la imagen esté disponible):

```bash
docker run -d \
  --name legaldev \
  --restart unless-stopped \
  -p 8000:8000 \
  -e GROQ_API_KEY=gsk_xxxxxxxxxxxxxxxxxxxx \
  ghcr.io/gustavintavo8/legaldev:latest
```

Si quiere pararla:
```bash
docker stop legaldev && docker rm legaldev
```

Ver logs:
```bash
docker logs -f legaldev
```

---

## Si no tiene Docker

Requisitos mínimos alternativos:

```
Python 3.11 o superior
uv (instalador: pip install uv)
Git
```

Pasos:
```bash
git clone https://github.com/gustavintavo8/legaldev
cd legaldev
uv sync
cp .env.example .env   # editar con la GROQ_API_KEY
uv run uvicorn app.main:app --host 0.0.0.0 --port 8000
```

La primera vez descarga los modelos (~160 MB) y tarda ~2 min. Las siguientes arranca en ~10s.

---

## Opción Cloudflare Tunnel (recomendada si no tiene IP pública)

1. El amigo instala `cloudflared` en el servidor: https://pkg.cloudflare.com/
2. Crea un túnel:
   ```bash
   cloudflared tunnel --url http://localhost:8000
   ```
3. Cloudflare le da una URL pública tipo `https://xxx-xxx.trycloudflare.com`
4. Esa URL se configura en la Streamlit como `API_URL`

No requiere cuenta, no requiere abrir puertos, gratis. El único límite es que la URL cambia si se reinicia el comando (solucionable con cuenta gratuita de Cloudflare y un túnel persistente).
