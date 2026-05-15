import json as _json
import logging
import time as _time
from contextlib import asynccontextmanager
from pathlib import Path
from pathlib import Path as _Path

from fastapi import APIRouter, Depends, FastAPI, Header, HTTPException, Request
from fastapi import Response as FastAPIResponse
from fastapi.middleware.cors import CORSMiddleware
from langchain_chroma import Chroma
from langchain_groq import ChatGroq
from langchain_huggingface import HuggingFaceEmbeddings
from prometheus_fastapi_instrumentator import Instrumentator
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from slowapi.util import get_remote_address

from app import cache as _cache
from app import store
from app.config import settings
from app.middleware import RequestIDMiddleware
from app.models import FeedbackInput, QuestionnaireInput, RAGResponse
from app.rag import run_pipeline

logging.basicConfig(level=getattr(logging, settings.log_level.upper(), logging.INFO))
logger = logging.getLogger(__name__)

EMBEDDING_MODEL = "paraphrase-multilingual-MiniLM-L12-v2"
CHROMA_COLLECTION = "legaldev"


def _get_real_ip(request: Request) -> str:
    if settings.trust_proxy_headers:
        xff = request.headers.get("x-forwarded-for")
        if xff:
            return xff.split(",")[0].strip()
    return get_remote_address(request)


limiter = Limiter(key_func=_get_real_ip)

_deep_health_cache: dict = {}
_DEEP_HEALTH_TTL = 60.0

FEEDBACK_FILE = _Path("feedback.jsonl")


def _verify_api_key(x_api_key: str | None = Header(default=None)) -> None:
    key_set = settings.api_key_set
    if not key_set:
        return
    if x_api_key is None:
        raise HTTPException(status_code=401, detail="X-API-Key header required")
    if x_api_key not in key_set:
        raise HTTPException(status_code=403, detail="Invalid API key")


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Loading embedding model: %s", EMBEDDING_MODEL)
    app.state.embeddings = HuggingFaceEmbeddings(
        model_name=EMBEDDING_MODEL, encode_kwargs={"normalize_embeddings": True}
    )
    logger.info("Connecting to ChromaDB at %s", settings.chroma_db_path)
    app.state.vectorstore = Chroma(
        persist_directory=settings.chroma_db_path,
        embedding_function=app.state.embeddings,
        collection_name=CHROMA_COLLECTION,
    )
    logger.info("Initializing Groq client with model %s", settings.groq_model)
    app.state.groq_client = ChatGroq(
        api_key=settings.groq_api_key,
        model_name=settings.groq_model,
        timeout=settings.groq_timeout,
        temperature=settings.groq_temperature,
        max_tokens=settings.groq_max_tokens,
    )
    logger.info(
        "Rate limit IP source: %s",
        "X-Forwarded-For (TRUST_PROXY_HEADERS=true)"
        if settings.trust_proxy_headers
        else "direct connection IP (TRUST_PROXY_HEADERS=false)",
    )
    count = store.count(app.state.vectorstore)
    if count == 0:
        raise RuntimeError(
            f"ChromaDB at '{settings.chroma_db_path}' is empty. Run 'make ingest' first."
        )
    app.state.indexed_normativas = frozenset(
        Path(s).stem for s in store.list_sources(app.state.vectorstore)
    )
    logger.info(
        "Indexed normativas: %d unique sources", len(app.state.indexed_normativas)
    )
    app.state.corpus_version = store.read_corpus_version(settings.chroma_db_path)
    logger.info("Corpus version: %s", app.state.corpus_version)
    logger.info("LegalDev is ready — %d chunks indexed", count)
    yield


app = FastAPI(
    title="LegalDev",
    version="0.2.0",
    description="Asistente RAG de normativa legal para developers en España",
    lifespan=lifespan,
)

app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_methods=["GET", "POST"],
    allow_headers=["Content-Type", "Authorization", "X-API-Key"],
)
app.add_middleware(RequestIDMiddleware)

Instrumentator().instrument(app).expose(app)


async def _analyze_handler(input: QuestionnaireInput, request: Request) -> RAGResponse:
    return await run_pipeline(input, request.app.state)


def _normativas_handler(request: Request) -> dict:
    try:
        sources = store.list_sources(request.app.state.vectorstore)
        return {"normativas": sources, "total": len(sources)}
    except Exception:
        return {"normativas": [], "total": 0}


@app.get("/")
def root():
    return {
        "name": "LegalDev",
        "version": "0.2.0",
        "description": "Asistente RAG de normativa legal para developers en España",
    }


@app.get("/health")
def health(request: Request):
    try:
        docs_indexed = store.count(request.app.state.vectorstore)
    except Exception:
        docs_indexed = -1
    return {
        "status": "ok",
        "docs_indexed": docs_indexed,
        "corpus_version": request.app.state.corpus_version,
    }


@app.get("/normativas")
def normativas(request: Request):
    return _normativas_handler(request)


@app.get("/health/deep")
def health_deep(request: Request):
    cached = _deep_health_cache.get("result")
    if (
        cached
        and _time.monotonic() - _deep_health_cache.get("ts", 0.0) < _DEEP_HEALTH_TTL
    ):
        return cached

    result: dict = {
        "chroma": "ok",
        "groq": "ok",
        "corpus_version": request.app.state.corpus_version,
    }

    try:
        store.count(request.app.state.vectorstore)
    except Exception as e:
        result["chroma"] = f"error: {type(e).__name__}"

    try:
        from langchain_core.messages import HumanMessage as _HumanMessage

        request.app.state.groq_client.invoke([_HumanMessage(content="ping")])
    except Exception as e:
        result["groq"] = f"error: {type(e).__name__}"

    _deep_health_cache["result"] = result
    _deep_health_cache["ts"] = _time.monotonic()
    return result


v1 = APIRouter(prefix="/v1", tags=["v1"])


@v1.post("/analyze", response_model=RAGResponse)
@limiter.limit(settings.rate_limit)
async def analyze_v1(
    input: QuestionnaireInput,
    request: Request,
    response: FastAPIResponse,
    _: None = Depends(_verify_api_key),
):
    cache_key = _cache.make_key(input.model_dump_json())
    cached = _cache.get(cache_key)
    if cached is not None:
        response.headers["X-Cache"] = "HIT"
        return cached
    result = await _analyze_handler(input, request)
    _cache.set(cache_key, result)
    response.headers["X-Cache"] = "MISS"
    return result


@v1.post("/feedback", status_code=201)
def feedback_v1(input: FeedbackInput):
    entry = input.model_dump()
    with FEEDBACK_FILE.open("a", encoding="utf-8") as f:
        f.write(_json.dumps(entry) + "\n")
    return {"status": "ok"}


app.include_router(v1)
