"""Latencia por MCP de ``analizar_proyecto`` y ``consultar_obligaciones`` (RNF-19, PT2-latencia).

Mide tres series contra un servidor ``/mcp`` (el Space o uno local), con peticiones de la
revisión 2026-07-28, y escribe un JSON con ``n``, ``p50``, ``p95``, mínimo y máximo de cada
una y la fecha:

* ``analizar_frio``: ``analizar_proyecto`` con cuestionarios distintos que no están en la
  caché. Cada cuestionario lleva en la descripción una marca de la ejecución
  («Medición de latencia <marca>-<n>.»), así que repetir la medición dentro de la hora que
  dura la caché no devuelve respuestas guardadas. Cada llamada es una llamada a Groq.
* ``analizar_caliente``: los mismos cuestionarios otra vez, que salen de la caché común. Se
  comprueba que vienen de ella: ``generado_por_ia.fecha`` tiene que ser la de la llamada en
  frío (una respuesta de la caché conserva la suya). Si no coincide, la llamada se cuenta
  aparte (``fuera_de_cache``) y no entra en los percentiles.
* ``consultar_obligaciones``: pares de normativa y contexto, sin modelo y sin caché.

Antes de medir, ``despertar`` espera a que ``/health`` responda (el Space se duerme por
inactividad y tarda en arrancar) y hace ``server/discover`` y ``tools/list``. Ese tiempo se
anota aparte y no entra en ninguna serie.

Los errores (429 del limitador, resultados con ``isError``, errores JSON-RPC y fallos de red)
se cuentan en ``excluidas`` y no entran en los percentiles. Los resultados sin cobertura
tampoco, porque no llaman al modelo.

Percentiles por el método del rango más cercano: el valor p de una muestra ordenada de n
tiempos es el de la posición ⌈p·n/100⌉. Siempre es un tiempo observado; con menos de 20
muestras, el p95 es el máximo.

Cuota. ``RATE_LIMIT`` (10 por minuto) y ``MCP_DAILY_LIMIT`` cuentan todas las llamadas a
``analizar_proyecto`` de la clave, también las que salen de la caché: una ejecución gasta
``--frio`` + ``--caliente`` del tope diario. Por eso las llamadas van espaciadas (90 s entre
las de frío, como PP-18, para no agotar la cuota gratuita de Groq; 8 s entre las de
caliente) y no se reintenta nada.

Configuración por variables de entorno (las mismas que ``docs/mcp/clients/claude-code.mcp.json``):

* ``LEGALDEV_URL``: la URL base del servidor (``https://gustavintavo8-legaldev.hf.space`` o
  ``http://127.0.0.1:8000``), con o sin ``/mcp`` al final.
* ``LEGALDEV_API_KEY``: la clave de ``/mcp``. No se imprime ni se guarda.

Uso, desde la raíz del repositorio:

    uv run python tools/medir_latencia_mcp.py --salida docs/mcp/latencia/resultado-AAAA-MM-DD.json
    uv run python tools/medir_latencia_mcp.py --frio 0 --caliente 0 --consultas 10  # sin Groq

El script no importa ``app`` ni lee ``.env``: solo habla HTTP con el servidor.
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import math
import os
import sys
import time
import uuid
from collections import Counter
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import httpx

# Revisión que se pide (la de app.mcp_server.PROTOCOL_VERSION; lo comprueba una prueba).
PROTOCOLO = "2026-07-28"
CLIENTE = {"name": "legaldev-medir-latencia", "version": "1"}
HERRAMIENTAS = ("analizar_proyecto", "listar_normativas", "consultar_obligaciones")

# Topes de una ejecución, para no gastar por error la cuota de Groq ni el tope diario.
MAX_FRIO = 20
MAX_CALIENTE = 50
MAX_CONSULTAS = 50

ESPERA_FRIO_S = 90.0
# RATE_LIMIT es 10 por minuto y cuenta también los aciertos de caché: 8 s dejan 7-8 por minuto.
ESPERA_CALIENTE_S = 8.0
ESPERA_CONSULTA_S = 2.0
TIMEOUT_LLAMADA_S = 300.0
TIMEOUT_DESPERTAR_S = 900.0
METODO_PERCENTIL = (
    "rango más cercano: el valor p de n tiempos ordenados es el de la posición "
    "ceil(p*n/100); con n < 20, p95 es el máximo"
)

_BASE: dict[str, Any] = {
    "tiene_usuarios_registrados": True,
    "acceso_publico": True,
    "usuarios_menores": False,
    "usuarios_ue": True,
    "transferencia_datos_terceros": False,
    "usa_ia": False,
    "tipo_ia": None,
    "usa_cookies": True,
    "monetizacion": "suscripcion",
    "contenido_digital": False,
    "ccaa": "Asturias",
    "es_empresa": True,
    "colegiado": None,
}
# Proyectos distintos, para que las llamadas en frío no recuperen siempre lo mismo.
PROYECTOS: tuple[dict[str, Any], ...] = (
    {
        "tipo_proyecto": "app_web",
        "descripcion_breve": "Reservas de citas para clínicas dentales con registro de pacientes.",
        "tipos_datos_personales": ["nombre", "email", "salud"],
    },
    {
        "tipo_proyecto": "ecommerce",
        "descripcion_breve": "Tienda en línea de material deportivo con pago con tarjeta.",
        "tipos_datos_personales": ["nombre", "email", "financieros"],
        "ccaa": "Madrid",
        "monetizacion": "pago_unico",
    },
    {
        "tipo_proyecto": "saas",
        "descripcion_breve": "Asistente que redacta respuestas a clientes con un modelo de lenguaje.",
        "tipos_datos_personales": ["nombre", "email"],
        "usa_ia": True,
        "tipo_ia": "generativa",
        "transferencia_datos_terceros": True,
        "ccaa": "Cataluña",
    },
    {
        "tipo_proyecto": "app_movil",
        "descripcion_breve": "Aplicación de rutas en bicicleta que guarda la ubicación del usuario.",
        "tipos_datos_personales": ["nombre", "ubicacion"],
        "usuarios_menores": True,
        "monetizacion": "freemium",
        "ccaa": "Andalucía",
        "es_empresa": False,
        "colegiado": True,
    },
    {
        "tipo_proyecto": "api",
        "descripcion_breve": "API de facturación electrónica para pequeñas empresas.",
        "tipos_datos_personales": ["nombre", "financieros"],
        "acceso_publico": False,
        "usa_cookies": False,
        "ccaa": "Galicia",
    },
)
# Consultas de consultar_obligaciones; se usan las de normativas que estén en el índice.
CONSULTAS: tuple[tuple[str, str], ...] = (
    ("RGPD", "registro de usuarios con email"),
    ("LSSI", "envío de comunicaciones comerciales por email"),
    ("EU AI Act", "sistema de IA generativa que redacta textos"),
    ("LOPDGDD", "consentimiento de menores de edad"),
    (
        "Guía sobre uso de cookies - AEPD",
        "banner de consentimiento para cookies analíticas",
    ),
    ("RGPD", "notificación de una brecha de seguridad"),
    ("Directiva NIS2", "gestión de incidentes de ciberseguridad"),
    ("LSSI", "información que debe mostrar la web del prestador"),
)


# --------------------------------------------------------------------------------------
# Cálculo
# --------------------------------------------------------------------------------------


def percentil(valores: list[float], p: float) -> float | None:
    """Percentil ``p`` (0-100] por el método del rango más cercano; ``None`` sin muestras."""
    if not 0 < p <= 100:
        raise ValueError("p tiene que estar en (0, 100]")
    if not valores:
        return None
    ordenados = sorted(valores)
    return ordenados[max(1, math.ceil(p * len(ordenados) / 100)) - 1]


def resumen(segundos: list[float]) -> dict[str, Any]:
    """``n``, ``p50``, ``p95``, mínimo y máximo, en segundos con tres decimales."""

    def _r(v: float | None) -> float | None:
        return None if v is None else round(v, 3)

    return {
        "n": len(segundos),
        "p50": _r(percentil(segundos, 50)),
        "p95": _r(percentil(segundos, 95)),
        "min": _r(min(segundos, default=None)),
        "max": _r(max(segundos, default=None)),
    }


def url_mcp(base: str) -> str:
    """``<base>/mcp`` a partir de la base con o sin ``/mcp`` (y sin barra final)."""
    base = base.strip().rstrip("/")
    return base if base.endswith("/mcp") else f"{base}/mcp"


def cuestionarios(n: int, marca: str) -> list[dict[str, Any]]:
    """``n`` cuestionarios distintos entre sí y de los de otras ejecuciones (``marca``)."""
    salida = []
    for i in range(n):
        proyecto = PROYECTOS[i % len(PROYECTOS)]
        cuestionario = {**_BASE, **proyecto}
        cuestionario["descripcion_breve"] = (
            f"{proyecto['descripcion_breve']} Medición de latencia {marca}-{i + 1}."
        )
        salida.append(cuestionario)
    return salida


def consultas(n: int, indexadas: set[str]) -> list[tuple[str, str]]:
    """``n`` consultas sobre normativas del índice (de ``CONSULTAS``, en ciclo)."""
    disponibles = [c for c in CONSULTAS if c[0] in indexadas]
    if not disponibles:
        disponibles = [
            (norma, "obligaciones principales") for norma in sorted(indexadas)
        ]
    if not disponibles:
        return []
    return [disponibles[i % len(disponibles)] for i in range(n)]


# --------------------------------------------------------------------------------------
# Protocolo
# --------------------------------------------------------------------------------------


@dataclass
class Llamada:
    """Una petición a ``/mcp``: el código HTTP, el mensaje JSON-RPC y lo que tardó."""

    http: int | None
    mensaje: dict[str, Any] | None
    segundos: float
    fallo: str | None = None


def _mensaje(respuesta: httpx.Response) -> dict[str, Any]:
    """El mensaje JSON-RPC con ``id``, venga como JSON o como flujo SSE."""
    if respuesta.headers.get("content-type", "").startswith("text/event-stream"):
        datos = [
            json.loads(linea[len("data:") :].strip())
            for linea in respuesta.text.splitlines()
            if linea.startswith("data:")
        ]
        return [d for d in datos if "id" in d][-1]
    return respuesta.json()


class SesionMCP:
    """Peticiones sueltas a ``/mcp`` de la revisión 2026-07-28 (sin estado: un POST cada una)."""

    def __init__(self, cliente: httpx.Client, url: str, clave: str) -> None:
        self.cliente = cliente
        self.url = url
        self._clave = clave
        self._id = 0

    def llamar(self, metodo: str, params: dict[str, Any] | None = None) -> Llamada:
        self._id += 1
        params = dict(params or {})
        params["_meta"] = {
            "io.modelcontextprotocol/protocolVersion": PROTOCOLO,
            "io.modelcontextprotocol/clientCapabilities": {},
            "io.modelcontextprotocol/clientInfo": CLIENTE,
        }
        cabeceras = {
            "Accept": "application/json, text/event-stream",
            "Content-Type": "application/json",
            "X-API-Key": self._clave,
            "MCP-Protocol-Version": PROTOCOLO,
            "Mcp-Method": metodo,
        }
        if metodo == "tools/call":
            cabeceras["Mcp-Name"] = params["name"]
        cuerpo = {"jsonrpc": "2.0", "id": self._id, "method": metodo, "params": params}
        t0 = time.perf_counter()
        try:
            r = self.cliente.post(self.url, json=cuerpo, headers=cabeceras)
            segundos = time.perf_counter() - t0
        except httpx.HTTPError as exc:
            return Llamada(None, None, time.perf_counter() - t0, type(exc).__name__)
        try:
            mensaje = _mensaje(r)
        except (ValueError, IndexError):
            mensaje = None
        return Llamada(r.status_code, mensaje, segundos)


def clasificar(llamada: Llamada) -> tuple[str, dict[str, Any]]:
    """``("ok", resultado)`` o ``(motivo de exclusión, {})``.

    Motivos: ``fallo_red:<excepción>``, ``http_<código>``, ``jsonrpc_<código>`` e
    ``is_error:<código estable>`` (el que va entre corchetes al principio del texto).
    """
    if llamada.fallo:
        return f"fallo_red:{llamada.fallo}", {}
    if llamada.http != 200 or llamada.mensaje is None:
        return f"http_{llamada.http}", {}
    if "error" in llamada.mensaje:
        return f"jsonrpc_{llamada.mensaje['error'].get('code')}", {}
    resultado = llamada.mensaje.get("result") or {}
    if resultado.get("isError"):
        texto = "".join(c.get("text", "") for c in resultado.get("content", []))
        return f"is_error:{texto.split(']')[0].lstrip('[') or '?'}", {}
    return "ok", resultado


# --------------------------------------------------------------------------------------
# Medición
# --------------------------------------------------------------------------------------


def _esperar_salud(
    cliente: httpx.Client, url: str, dormir: Callable[[float], None], limite_s: float
) -> float:
    """Segundos hasta que ``/health`` responde 200 (el Space puede estar dormido)."""
    t0 = time.perf_counter()
    while True:
        try:
            if cliente.get(url).status_code == 200:
                return time.perf_counter() - t0
        except httpx.HTTPError:
            pass
        if time.perf_counter() - t0 > limite_s:
            raise TimeoutError(f"{url} no respondió 200 en {limite_s:.0f} s")
        dormir(5)


def _resultado_tools(estructurado: dict[str, Any]) -> dict[str, Any]:
    generado = estructurado.get("generado_por_ia") or {}
    return {
        "llm_model": estructurado.get("llm_model"),
        "fecha_generacion": generado.get("fecha"),
        "sin_cobertura": bool(estructurado.get("sin_cobertura")),
    }


def medir(
    cliente: httpx.Client,
    base: str,
    clave: str,
    *,
    n_frio: int = 10,
    n_caliente: int = 10,
    n_consultas: int = 10,
    espera_frio: float = ESPERA_FRIO_S,
    espera_caliente: float = ESPERA_CALIENTE_S,
    espera_consulta: float = ESPERA_CONSULTA_S,
    dormir: Callable[[float], None] = time.sleep,
    marca: str | None = None,
    avisar: Callable[[str], None] = lambda _: None,
) -> dict[str, Any]:
    """Despierta el servidor, mide las tres series y devuelve el informe (sin la clave)."""
    if not 0 <= n_frio <= MAX_FRIO:
        raise ValueError(f"--frio tiene que estar entre 0 y {MAX_FRIO}")
    if not 0 <= n_caliente <= MAX_CALIENTE:
        raise ValueError(f"--caliente tiene que estar entre 0 y {MAX_CALIENTE}")
    if not 0 <= n_consultas <= MAX_CONSULTAS:
        raise ValueError(f"--consultas tiene que estar entre 0 y {MAX_CONSULTAS}")
    if n_caliente and not n_frio:
        raise ValueError(
            "--caliente repite los cuestionarios de --frio: hace falta --frio > 0"
        )
    marca = marca or uuid.uuid4().hex[:8]
    base = base.strip().rstrip("/").removesuffix("/mcp")
    sesion = SesionMCP(cliente, url_mcp(base), clave)
    fecha = dt.datetime.now(dt.UTC).isoformat(timespec="seconds")

    # ------------------------------------------------------------------ despertar
    health_s = _esperar_salud(cliente, f"{base}/health", dormir, TIMEOUT_DESPERTAR_S)
    discover = sesion.llamar("server/discover")
    motivo, info = clasificar(discover)
    if motivo != "ok":
        raise RuntimeError(
            f"server/discover falló ({motivo}): ¿URL o clave incorrectas?"
        )
    lista = sesion.llamar("tools/list")
    motivo, tools = clasificar(lista)
    nombres = [t.get("name") for t in tools.get("tools", [])]
    if motivo != "ok" or set(nombres) != set(HERRAMIENTAS):
        raise RuntimeError(
            f"tools/list no devolvió las tres herramientas ({motivo}: {nombres})"
        )
    motivo, listado = clasificar(
        sesion.llamar("tools/call", {"name": "listar_normativas", "arguments": {}})
    )
    estructurado = listado.get("structuredContent") or {}
    indexadas = {n["identificador"] for n in estructurado.get("normativas", [])}
    servidor = (info.get("_meta") or {}).get("io.modelcontextprotocol/serverInfo") or {}
    avisar(
        f"Servidor listo: /health {health_s:.1f} s, {len(indexadas)} normativas, "
        f"corpus {estructurado.get('corpus_version')}"
    )

    llamadas: list[dict[str, Any]] = []
    excluidas: dict[str, Counter] = {
        s: Counter()
        for s in ("analizar_frio", "analizar_caliente", "consultar_obligaciones")
    }
    tiempos: dict[str, list[float]] = {s: [] for s in excluidas}
    ultima: float | None = None

    def _pausa(espera: float) -> None:
        nonlocal ultima
        if ultima is not None:
            pendiente = espera - (time.perf_counter() - ultima)
            if pendiente > 0:
                dormir(pendiente)
        ultima = time.perf_counter()

    def _anotar(serie: str, i: int, llamada: Llamada, motivo: str, extra: dict) -> None:
        fila = {
            "serie": serie,
            "i": i,
            "segundos": round(llamada.segundos, 3),
            "http": llamada.http,
            "resultado": motivo,
            **extra,
        }
        llamadas.append(fila)
        avisar(f"{serie} {i}: {fila['segundos']} s {motivo}")

    # ---------------------------------------------------------------- frío
    # Cuestionarios que dieron un informe en frío, con su fecha de generación (None si el
    # servidor no devuelve generado_por_ia, anterior al 12/11/2026).
    validos: list[tuple[dict[str, Any], str | None]] = []
    for i, cuestionario in enumerate(cuestionarios(n_frio, marca), start=1):
        _pausa(espera_frio)
        llamada = sesion.llamar(
            "tools/call", {"name": "analizar_proyecto", "arguments": cuestionario}
        )
        motivo, resultado = clasificar(llamada)
        extra: dict[str, Any] = {}
        if motivo == "ok":
            extra = _resultado_tools(resultado.get("structuredContent") or {})
            if extra["sin_cobertura"]:
                motivo = "sin_cobertura"
            else:
                validos.append((cuestionario, extra["fecha_generacion"]))
        if motivo == "ok":
            tiempos["analizar_frio"].append(llamada.segundos)
        else:
            excluidas["analizar_frio"][motivo] += 1
        _anotar("analizar_frio", i, llamada, motivo, extra)

    # ------------------------------------------------------------- caliente
    for i in range(1, n_caliente + 1):
        if not validos:
            excluidas["analizar_caliente"]["sin_informe_en_frio"] += n_caliente - i + 1
            break
        cuestionario, fecha_frio = validos[(i - 1) % len(validos)]
        _pausa(espera_caliente)
        llamada = sesion.llamar(
            "tools/call", {"name": "analizar_proyecto", "arguments": cuestionario}
        )
        motivo, resultado = clasificar(llamada)
        extra = {}
        if motivo == "ok":
            extra = _resultado_tools(resultado.get("structuredContent") or {})
            if fecha_frio is None:
                motivo = "cache_no_verificable"
            elif extra["fecha_generacion"] != fecha_frio:
                motivo = "fuera_de_cache"
            extra["desde_cache"] = motivo == "ok"
        if motivo == "ok":
            tiempos["analizar_caliente"].append(llamada.segundos)
        else:
            excluidas["analizar_caliente"][motivo] += 1
        _anotar("analizar_caliente", i, llamada, motivo, extra)

    # ------------------------------------------------------------- consultas
    for i, (normativa, contexto) in enumerate(
        consultas(n_consultas, indexadas), start=1
    ):
        _pausa(espera_consulta)
        llamada = sesion.llamar(
            "tools/call",
            {
                "name": "consultar_obligaciones",
                "arguments": {"normativa": normativa, "contexto": contexto},
            },
        )
        motivo, resultado = clasificar(llamada)
        extra = {"normativa": normativa}
        if motivo == "ok":
            fragmentos = (resultado.get("structuredContent") or {}).get(
                "fragmentos", []
            )
            extra["fragmentos"] = len(fragmentos)
            tiempos["consultar_obligaciones"].append(llamada.segundos)
        else:
            excluidas["consultar_obligaciones"][motivo] += 1
        _anotar("consultar_obligaciones", i, llamada, motivo, extra)

    return {
        "fecha": fecha,
        "servidor": base,
        "protocolo": PROTOCOLO,
        "version_servidor": servidor.get("version"),
        "corpus_version": estructurado.get("corpus_version"),
        "marca": marca,
        "metodo": {
            "percentil": METODO_PERCENTIL,
            "unidad": "segundos, del envío del POST a la llegada de la respuesta completa",
            "analizar_frio": "cuestionarios distintos, con la marca de la ejecución en la descripción",
            "analizar_caliente": "los de frío otra vez; cuentan si generado_por_ia.fecha coincide",
            "esperas_s": {
                "frio": espera_frio,
                "caliente": espera_caliente,
                "consulta": espera_consulta,
            },
            "reintentos": 0,
        },
        "despertar": {
            "health_s": round(health_s, 3),
            "discover_s": round(discover.segundos, 3),
            "tools_list_s": round(lista.segundos, 3),
        },
        "series": {
            serie: {**resumen(tiempos[serie]), "excluidas": dict(excluidas[serie])}
            for serie in tiempos
        },
        "llamadas": llamadas,
    }


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--frio", type=int, default=10, help="llamadas en frío (Groq)")
    ap.add_argument(
        "--caliente", type=int, default=10, help="llamadas en caliente (caché)"
    )
    ap.add_argument(
        "--consultas", type=int, default=10, help="llamadas a consultar_obligaciones"
    )
    ap.add_argument("--espera-frio", type=float, default=ESPERA_FRIO_S)
    ap.add_argument("--espera-caliente", type=float, default=ESPERA_CALIENTE_S)
    ap.add_argument("--espera-consulta", type=float, default=ESPERA_CONSULTA_S)
    ap.add_argument("--salida", help="fichero JSON donde guardar el resultado")
    args = ap.parse_args(argv)

    base = os.environ.get("LEGALDEV_URL", "").strip()
    clave = os.environ.get("LEGALDEV_API_KEY", "").strip()
    if not base or not clave:
        print("Faltan LEGALDEV_URL o LEGALDEV_API_KEY en el entorno.", file=sys.stderr)
        return 2
    print(
        f"Midiendo {url_mcp(base)}: {args.frio} en frío, {args.caliente} en caliente y "
        f"{args.consultas} consultas ({args.frio + args.caliente} del tope diario de la clave).",
        file=sys.stderr,
    )
    with httpx.Client(timeout=httpx.Timeout(TIMEOUT_LLAMADA_S, connect=30)) as cliente:
        try:
            informe = medir(
                cliente,
                base,
                clave,
                n_frio=args.frio,
                n_caliente=args.caliente,
                n_consultas=args.consultas,
                espera_frio=args.espera_frio,
                espera_caliente=args.espera_caliente,
                espera_consulta=args.espera_consulta,
                avisar=lambda m: print(m, file=sys.stderr, flush=True),
            )
        except (ValueError, RuntimeError, TimeoutError) as exc:
            print(f"Error: {exc}", file=sys.stderr)
            return 1
    texto = json.dumps(informe, ensure_ascii=False, indent=2)
    if args.salida:
        destino = Path(args.salida)
        destino.parent.mkdir(parents=True, exist_ok=True)
        destino.write_text(texto + "\n", encoding="utf-8")
        print(f"Resultado: {destino}", file=sys.stderr)
    print(texto)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
