"""Tokens por análisis y cuántos análisis caben en los límites de Groq (0.5.2).

Ejecuta ``--n`` análisis reales en proceso (por defecto 5), con el índice de este
repositorio y el modelo de ``.env`` (``GROQ_MODEL``), y escribe un JSON con:

* los tokens de cada informe (entrada, salida, razonamiento y total, los que el motor lee de
  la respuesta desde la 0.5.2, ``PipelineResult.uso_modelo``), su ``finish_reason`` y el
  ``usage`` numérico tal como lo devuelve Groq, para comprobar qué campos da;
* la media y el máximo de cada tipo de token, y cuántos informes se cortaron por longitud;
* los límites de la cuenta que Groq envía en las cabeceras ``x-ratelimit-*`` de una llamada
  mínima a ``chat/completions`` con el mismo modelo, y con ellos, cuántos análisis caben por
  minuto y por día.

Los cuestionarios son los de ``tools/medir_latencia_mcp.py`` (cinco proyectos), con la marca
de la ejecución en la descripción: son distintos entre sí y de los de otras ejecuciones, así
que ninguno sale de la caché de respuestas (si alguno saliera, se anota como ``cache`` y no
cuenta). Van por ``service.analyze``, el mismo camino que ``POST /v1/analyze`` y
``analizar_proyecto``.

Cuántas llamadas a Groq gasta: ``--n`` + 1 (la mínima, que va primero, y una por análisis).
Sin reintentos (el cliente de Groq se crea con ``max_retries=0``; ``ChatGroq`` reintenta dos
veces por defecto), sin modelo de respaldo (``GROQ_FALLBACK_MODEL`` vacío) y sin la
comprobación del modelo al arrancar (``GROQ_VERIFY_MODEL_ON_STARTUP=false``). Las llamadas
van espaciadas ``--espera`` segundos (90 por defecto, como PP-18 y la latencia). Un análisis
sin cobertura no llama al modelo.

Los límites. Según la documentación de Groq («Rate Limits», cabeceras de la respuesta),
``x-ratelimit-limit-requests`` es el límite de peticiones por día (RPD) y
``x-ratelimit-limit-tokens`` el de tokens por minuto (TPM); ``remaining-*`` es lo que queda
y ``reset-*``, cuándo se repone. Se guardan las cabeceras tal cual, para poder comprobarlo.
Las peticiones por minuto (RPM) y los tokens por día (TPD) no van en las cabeceras: se pasan
con ``--rpm`` y ``--tpd`` (consola de Groq, página de límites de la organización); si no, el
cálculo los deja en ``null``. Cada análisis es una petición.

La clave de Groq la lee ``app.config.settings`` del ``.env``. No se imprime ni se guarda: el
JSON no lleva la clave ni texto de los informes, solo recuentos. Una clave con espacios o
saltos de línea al principio o al final, o con caracteres no ASCII o de control, se rechaza
antes de la primera llamada, sin mostrarla (httpx rechazaría la cabecera con un error que la
repite entera). De un error de red o de httpx solo se imprime el tipo, nunca el mensaje.

Uso, desde la raíz del repositorio (hace falta el índice y ``GROQ_API_KEY`` en ``.env``):

    uv run python tools/medir_tokens.py [--n 5] [--espera 90] [--rpm 30] [--tpd 200000]
        [--salida docs/mcp/tokens/resultado-AAAA-MM-DD-<commit>.json]

Por defecto guarda en ``docs/mcp/tokens/resultado-AAAA-MM-DD-<commit>.json`` y nunca
sobrescribe un resultado: el destino se comprueba antes de cualquier llamada. Al terminar,
``chroma_db/chroma.sqlite3`` puede quedar modificado (Chroma lo abre en escritura): se
restaura con ``git checkout -- chroma_db/chroma.sqlite3``.
"""

from __future__ import annotations

import argparse
import asyncio
import datetime as dt
import json
import math
import os
import subprocess
import sys
import time
import uuid
from collections import Counter
from collections.abc import Callable, Mapping
from pathlib import Path
from typing import Any

import httpx

RAIZ = Path(__file__).resolve().parent.parent
if str(RAIZ) not in sys.path:
    sys.path.insert(0, str(RAIZ))

from tools.medir_latencia_mcp import cuestionarios  # noqa: E402

URL_GROQ = "https://api.groq.com/openai/v1/chat/completions"
MAX_INFORMES = 20
ESPERA_S = 90.0
# Tokens de salida de la llamada mínima: solo interesan sus cabeceras.
MAX_TOKENS_MINIMA = 16
TIPOS = ("entrada", "salida", "razonamiento", "total")
MAPA_CABECERAS = {
    "x-ratelimit-limit-requests": "peticiones por día (RPD)",
    "x-ratelimit-limit-tokens": "tokens por minuto (TPM)",
    "x-ratelimit-remaining-requests": "peticiones que quedan hoy",
    "x-ratelimit-remaining-tokens": "tokens que quedan en este minuto",
    "x-ratelimit-reset-requests": "cuándo se repone el límite de peticiones",
    "x-ratelimit-reset-tokens": "cuándo se repone el límite de tokens",
}


# --------------------------------------------------------------------------------------
# Límites de Groq
# --------------------------------------------------------------------------------------


def _entero(valor: Any) -> int | None:
    try:
        return int(str(valor).strip())
    except (TypeError, ValueError):
        return None


def limites_de_cabeceras(cabeceras: Mapping[str, str]) -> dict[str, Any]:
    """RPD, TPM, lo que queda y cuándo se repone, de las cabeceras ``x-ratelimit-*``.

    ``None`` en lo que falte o no sea un número. El significado de cada cabecera es el de
    ``MAPA_CABECERAS`` (documentación de Groq).
    """
    c = {k.lower(): v for k, v in cabeceras.items()}
    return {
        "rpd": _entero(c.get("x-ratelimit-limit-requests")),
        "tpm": _entero(c.get("x-ratelimit-limit-tokens")),
        "restantes_rpd": _entero(c.get("x-ratelimit-remaining-requests")),
        "restantes_tpm": _entero(c.get("x-ratelimit-remaining-tokens")),
        "reposicion_rpd": c.get("x-ratelimit-reset-requests"),
        "reposicion_tpm": c.get("x-ratelimit-reset-tokens"),
    }


def _numeros(valor: Any) -> Any:
    """Solo los números (y diccionarios de números) de un ``usage``: nada de texto."""
    if isinstance(valor, bool):
        return None
    if isinstance(valor, int | float):
        return valor
    if isinstance(valor, Mapping):
        limpio = {str(k): _numeros(v) for k, v in valor.items()}
        return {k: v for k, v in limpio.items() if v is not None} or None
    return None


def leer_limites(
    cliente: httpx.Client,
    clave: str,
    modelo: str,
    *,
    reasoning_effort: str | None = None,
) -> dict[str, Any]:
    """Una llamada mínima a ``chat/completions`` para leer las cabeceras de límites.

    Con el mismo modelo que los análisis, porque los límites son por modelo. Devuelve el
    código HTTP, las cabeceras ``x-ratelimit-*`` y ``retry-after`` tal cual, los límites ya
    leídos y el ``usage`` numérico de la llamada. Nunca la clave.
    """
    cuerpo: dict[str, Any] = {
        "model": modelo,
        "messages": [{"role": "user", "content": "Responde solo: ok"}],
        "max_tokens": MAX_TOKENS_MINIMA,
        "temperature": 0,
    }
    if reasoning_effort and modelo.startswith("openai/gpt-oss"):
        cuerpo["reasoning_effort"] = reasoning_effort
    respuesta = cliente.post(
        URL_GROQ, json=cuerpo, headers={"Authorization": f"Bearer {clave}"}
    )
    cabeceras = {
        k.lower(): v
        for k, v in respuesta.headers.items()
        if k.lower().startswith("x-ratelimit-") or k.lower() == "retry-after"
    }
    uso = None
    if respuesta.status_code == 200:
        try:
            uso = _numeros(respuesta.json().get("usage"))
        except ValueError:
            uso = None
    return {
        "http": respuesta.status_code,
        "modelo": modelo,
        "cabeceras": cabeceras,
        "significado": MAPA_CABECERAS,
        **limites_de_cabeceras(cabeceras),
        "usage_llamada_minima": uso,
    }


# --------------------------------------------------------------------------------------
# Cálculo
# --------------------------------------------------------------------------------------


def resumen(informes: list[dict[str, Any]]) -> dict[str, Any]:
    """Media y máximo de cada tipo de token entre los informes válidos, y los cortes."""
    validos = [f for f in informes if f["resultado"] == "ok"]
    salida: dict[str, Any] = {
        "n": len(informes),
        "con_informe": len(validos),
        "truncados": sum(f.get("finish_reason") == "length" for f in validos),
        "finish_reason": dict(Counter(str(f.get("finish_reason")) for f in validos)),
        "excluidos": dict(
            Counter(f["resultado"] for f in informes if f["resultado"] != "ok")
        ),
    }
    for tipo in TIPOS:
        valores = [
            f["tokens"][tipo] for f in validos if f["tokens"].get(tipo) is not None
        ]
        salida[tipo] = {
            "n": len(valores),
            "media": round(sum(valores) / len(valores), 1) if valores else None,
            "max": max(valores, default=None),
        }
    return salida


def _caben(limite: int | None, por_analisis: float | None) -> int | None:
    if not limite or not por_analisis:
        return None
    return math.floor(limite / por_analisis)


def _minimo(*valores: int | None) -> int | None:
    presentes = [v for v in valores if v is not None]
    return min(presentes) if presentes else None


def capacidad(
    res: dict[str, Any],
    limites: dict[str, Any],
    *,
    rpm: int | None = None,
    tpd: int | None = None,
    max_tokens: int | None = None,
) -> dict[str, Any]:
    """Cuántos análisis caben por minuto y por día con los límites de la cuenta.

    Cada análisis es una petición y gasta ``total`` tokens (entrada más salida). La cifra de
    cada ventana es la más baja de las que se conocen, con el máximo observado (el caso
    peor); con la media va aparte. Si Groq reservara al recibir la petición la entrada más
    ``max_tokens`` (no lo documenta), por minuto cabrían ``reservando_max_tokens``.
    """
    total = res.get("total") or {}
    media, maximo = total.get("media"), total.get("max")
    entrada_max = (res.get("entrada") or {}).get("max")
    tpm, rpd = limites.get("tpm"), limites.get("rpd")
    reserva = entrada_max + max_tokens if entrada_max and max_tokens else None
    por_minuto = {
        "por_tokens_con_media": _caben(tpm, media),
        "por_tokens_con_maximo": _caben(tpm, maximo),
        "por_peticiones": rpm,
        "reservando_max_tokens": _caben(tpm, reserva),
    }
    por_dia = {
        "por_peticiones": rpd,
        "por_tokens_con_media": _caben(tpd, media),
        "por_tokens_con_maximo": _caben(tpd, maximo),
    }
    return {
        "limites_usados": {"tpm": tpm, "rpd": rpd, "rpm": rpm, "tpd": tpd},
        "tokens_por_analisis": {"media": media, "max": maximo},
        "por_minuto": {
            **por_minuto,
            "cifra": _minimo(por_minuto["por_tokens_con_maximo"], rpm),
        },
        "por_dia": {
            **por_dia,
            "cifra": _minimo(rpd, por_dia["por_tokens_con_maximo"]),
        },
        "formulas": {
            "por_minuto": "min(floor(TPM / max(total)), RPM)",
            "por_dia": "min(RPD, floor(TPD / max(total)))",
            "con_media": "igual, con la media de total en lugar del máximo",
            "reservando_max_tokens": "floor(TPM / (max(entrada) + GROQ_MAX_TOKENS))",
            "nulos": "un límite que no se conoce (RPM y TPD sin --rpm y --tpd) no entra",
        },
    }


# --------------------------------------------------------------------------------------
# Medición
# --------------------------------------------------------------------------------------


class _Registro:
    """Envuelve el cliente de Groq: cuenta las llamadas y guarda la última respuesta."""

    def __init__(self, cliente: Any) -> None:
        self.cliente = cliente
        self.llamadas = 0
        self.ultima: Any = None

    def invoke(self, mensajes: Any) -> Any:
        self.llamadas += 1
        self.ultima = self.cliente.invoke(mensajes)
        return self.ultima


def _usage_groq(respuesta: Any) -> Any:
    metadatos = getattr(respuesta, "response_metadata", None)
    if not isinstance(metadatos, Mapping):
        return None
    return _numeros(metadatos.get("token_usage"))


def medir(
    state: Any,
    n: int,
    *,
    marca: str,
    espera: float = ESPERA_S,
    dormir: Callable[[float], None] = time.sleep,
    avisar: Callable[[str], None] = lambda _: None,
) -> tuple[list[dict[str, Any]], int]:
    """``n`` análisis por ``service.analyze``; devuelve las filas y las llamadas al modelo."""
    from app import service
    from app.models import QuestionnaireInput

    registro = _Registro(state.groq_client)
    state.groq_client = registro
    informes: list[dict[str, Any]] = []
    ultima: float | None = None
    for i, cuestionario in enumerate(cuestionarios(n, marca), start=1):
        if ultima is not None:
            pendiente = espera - (time.perf_counter() - ultima)
            if pendiente > 0:
                dormir(pendiente)
        ultima = time.perf_counter()
        registro.ultima = None
        fila: dict[str, Any]
        try:
            analisis = asyncio.run(
                service.analyze(
                    QuestionnaireInput.model_validate(cuestionario),
                    state,
                    via=service.Via.MCP,
                )
            )
        except service.NoCoverageError:
            fila = {"resultado": "sin_cobertura"}
        except Exception as exc:  # 429, 5xx, tiempo agotado: se anota y se sigue
            causa = exc.__cause__
            fila = {
                "resultado": f"error:{type(exc).__name__}",
                "causa": type(causa).__name__ if causa else None,
            }
        else:
            uso = analisis.result.uso_modelo
            fila = {
                "resultado": "cache" if analisis.cache_hit else "ok",
                "llm_model": analisis.result.response.llm_model,
                "finish_reason": uso.finish_reason,
                "tokens": {
                    "entrada": uso.tokens_entrada,
                    "salida": uso.tokens_salida,
                    "razonamiento": uso.tokens_razonamiento,
                    "total": uso.tokens_total,
                },
                "usage_groq": None
                if analisis.cache_hit
                else _usage_groq(registro.ultima),
            }
        fila = {
            "i": i,
            "tipo_proyecto": cuestionario["tipo_proyecto"],
            "segundos": round(time.perf_counter() - ultima, 1),
            **fila,
        }
        informes.append(fila)
        tokens = (fila.get("tokens") or {}).get("total")
        avisar(
            f"{i}/{n} {fila['tipo_proyecto']}: {fila['resultado']} "
            f"{fila.get('finish_reason') or ''} total={tokens} ({fila['segundos']} s)"
        )
    return informes, registro.llamadas


def ejecutar(
    n: int,
    *,
    clave: str,
    modelo: str,
    max_tokens: int,
    reasoning_effort: str | None,
    cliente_http: httpx.Client,
    cargar_motor: Callable[[], Any],
    espera: float = ESPERA_S,
    marca: str | None = None,
    rpm: int | None = None,
    tpd: int | None = None,
    commit: str = "desconocido",
    dormir: Callable[[float], None] = time.sleep,
    avisar: Callable[[str], None] = lambda _: None,
) -> dict[str, Any]:
    """La llamada mínima, el motor, los ``n`` análisis y el resultado (sin la clave).

    Si la llamada mínima no responde 200 (clave o modelo mal), se para antes de cargar el
    motor: solo se ha gastado esa llamada.
    """
    if not 1 <= n <= MAX_INFORMES:
        raise ValueError(f"--n tiene que estar entre 1 y {MAX_INFORMES}")
    marca = marca or uuid.uuid4().hex[:8]
    fecha = dt.datetime.now(dt.UTC).isoformat(timespec="seconds")
    limites = leer_limites(
        cliente_http, clave, modelo, reasoning_effort=reasoning_effort
    )
    if limites["http"] != 200:
        raise RuntimeError(
            f"La llamada mínima a Groq respondió {limites['http']}: no se mide nada"
        )
    avisar(
        f"Límites de {modelo}: {limites['tpm']} tokens por minuto, "
        f"{limites['rpd']} peticiones por día"
    )
    state = cargar_motor()
    informes, llamadas = medir(
        state, n, marca=marca, espera=espera, dormir=dormir, avisar=avisar
    )
    res = resumen(informes)
    return {
        "fecha": fecha,
        "commit": commit,
        "modelo": modelo,
        "max_tokens": max_tokens,
        "reasoning_effort": reasoning_effort,
        "corpus_version": getattr(state, "corpus_version", None),
        "marca": marca,
        "metodo": {
            "camino": "service.analyze en proceso (el de POST /v1/analyze y analizar_proyecto)",
            "cuestionarios": "los de tools/medir_latencia_mcp.py, con la marca en la descripción",
            "espera_s": espera,
            "reintentos": 0,
            "respaldo": None,
            "tokens": "PipelineResult.uso_modelo (usage_metadata de LangChain); usage_groq es el usage numérico de Groq",
        },
        "llamadas_groq": 1 + llamadas,
        "informes": informes,
        "resumen": res,
        "limites": limites,
        "capacidad": capacidad(res, limites, rpm=rpm, tpd=tpd, max_tokens=max_tokens),
    }


# --------------------------------------------------------------------------------------
# Programa
# --------------------------------------------------------------------------------------


def _commit() -> str:
    try:
        return subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"],
            cwd=RAIZ,
            capture_output=True,
            text=True,
            check=True,
        ).stdout.strip()
    except (OSError, subprocess.CalledProcessError):
        return "desconocido"


def destino(
    salida: Path | None, fecha: dt.date, commit: str, *, carpeta: Path | None = None
) -> Path:
    """``salida`` o ``resultado-AAAA-MM-DD-<commit>.json`` en ``carpeta`` (por defecto,
    ``docs/mcp/tokens``). Lanza ``FileExistsError`` si ya existe: nunca se sobrescribe."""
    carpeta = carpeta or RAIZ / "docs" / "mcp" / "tokens"
    ruta = salida or carpeta / f"resultado-{fecha.isoformat()}-{commit}.json"
    if ruta.exists():
        raise FileExistsError(
            f"{ruta} ya existe y no se sobrescribe un resultado; elige otro con --salida"
        )
    return ruta


def clave_bien_formada(clave: str) -> bool:
    """La clave se puede enviar tal cual en ``Authorization``: ASCII imprimible, sin espacios
    ni saltos de línea al principio o al final.

    ``Settings`` no recorta la clave, y una que llegue del ``.env`` con un espacio o un
    ``\\r`` al final la rechaza httpx (h11) con un error cuyo mensaje lleva la cabecera
    entera, ``Bearer <clave>``. Así se para antes de la primera llamada.
    """
    return clave == clave.strip() and clave.isascii() and clave.isprintable()


def _parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--n", type=int, default=5, help=f"análisis (1 a {MAX_INFORMES})")
    ap.add_argument(
        "--espera", type=float, default=ESPERA_S, help="segundos entre análisis"
    )
    ap.add_argument(
        "--rpm", type=int, default=None, help="peticiones por minuto de la cuenta"
    )
    ap.add_argument("--tpd", type=int, default=None, help="tokens por día de la cuenta")
    ap.add_argument(
        "--salida", type=Path, default=None, help="fichero JSON del resultado"
    )
    return ap


def _cargar_motor() -> Any:
    """El motor como en el ``lifespan``, con un cliente de Groq sin reintentos."""
    from types import SimpleNamespace

    from app import main as app_main
    from app.config import settings

    state = SimpleNamespace()
    app_main.load_engine(state)
    state.groq_client = app_main._make_groq_client(settings.groq_model, max_retries=0)
    state.groq_fallback_client = None
    return state


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    if not 1 <= args.n <= MAX_INFORMES:
        print(f"--n tiene que estar entre 1 y {MAX_INFORMES}", file=sys.stderr)
        return 2
    commit = _commit()
    try:  # antes de cualquier llamada: si ya existe, no se gasta nada
        fichero = destino(args.salida, dt.date.today(), commit)
    except FileExistsError as exc:
        print(exc, file=sys.stderr)
        return 2

    # Antes de importar app.config: el entorno manda sobre el .env (pydantic-settings).
    os.environ["GROQ_FALLBACK_MODEL"] = ""
    os.environ["GROQ_VERIFY_MODEL_ON_STARTUP"] = "false"
    os.environ.setdefault("LOG_LEVEL", "WARNING")
    from app.config import settings

    if not settings.groq_api_key.strip():
        print("Falta GROQ_API_KEY en .env.", file=sys.stderr)
        return 2
    if not clave_bien_formada(settings.groq_api_key):
        print(
            "GROQ_API_KEY tiene espacios o saltos de línea al principio o al final, o "
            "caracteres no ASCII o de control: corrígela en .env (no se muestra aquí).",
            file=sys.stderr,
        )
        return 2
    print(
        f"{args.n} análisis con {settings.groq_model}: {args.n + 1} llamadas a Groq "
        f"(la mínima y una por análisis), {args.espera:.0f} s entre análisis.",
        file=sys.stderr,
    )
    with httpx.Client(timeout=30) as cliente:
        try:
            resultado = ejecutar(
                args.n,
                clave=settings.groq_api_key,
                modelo=settings.groq_model,
                max_tokens=settings.groq_max_tokens,
                reasoning_effort=settings.groq_reasoning_effort or None,
                cliente_http=cliente,
                cargar_motor=_cargar_motor,
                espera=args.espera,
                rpm=args.rpm,
                tpd=args.tpd,
                commit=commit,
                avisar=lambda m: print(m, file=sys.stderr, flush=True),
            )
        except (httpx.HTTPError, UnicodeError) as exc:
            # Solo el tipo, como medir() y app.main._check_groq_model: el mensaje de httpx
            # puede llevar las cabeceras de la petición, con la clave («Illegal header value
            # b'Bearer …'»).
            print(f"Error: {type(exc).__name__} (sin el mensaje)", file=sys.stderr)
            return 1
        except (RuntimeError, ValueError) as exc:
            # Los de este script y los del motor (401 de la llamada mínima, índice vacío).
            print(f"Error: {type(exc).__name__}: {exc}", file=sys.stderr)
            return 1
    fichero.parent.mkdir(parents=True, exist_ok=True)
    with fichero.open("x", encoding="utf-8") as f:
        f.write(json.dumps(resultado, ensure_ascii=False, indent=2) + "\n")
    print(
        json.dumps(
            {
                "resumen": resultado["resumen"],
                "capacidad": {
                    k: resultado["capacidad"][k] for k in ("por_minuto", "por_dia")
                },
            },
            ensure_ascii=False,
        )
    )
    print(f"Resultado: {fichero}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
