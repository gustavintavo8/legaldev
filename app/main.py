import logging
from contextlib import asynccontextmanager

from fastapi import APIRouter, FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from langchain_chroma import Chroma
from langchain_groq import ChatGroq
from langchain_huggingface import HuggingFaceEmbeddings
from prometheus_fastapi_instrumentator import Instrumentator
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from slowapi.util import get_remote_address

from app.config import settings
from app.models import QuestionnaireInput, RAGResponse
from app.rag import run_pipeline

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

EMBEDDING_MODEL = "all-MiniLM-L6-v2"
CHROMA_COLLECTION = "legaldev"


def _get_real_ip(request: Request) -> str:
    if settings.trust_proxy_headers:
        xff = request.headers.get("x-forwarded-for")
        if xff:
            return xff.split(",")[0].strip()
    return get_remote_address(request)


limiter = Limiter(key_func=_get_real_ip)


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Loading embedding model: %s", EMBEDDING_MODEL)
    app.state.embeddings = HuggingFaceEmbeddings(model_name=EMBEDDING_MODEL)
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
    count = app.state.vectorstore._collection.count()
    if count == 0:
        raise RuntimeError(
            f"ChromaDB at '{settings.chroma_db_path}' is empty. Run 'make ingest' first."
        )
    logger.info("LegalDev is ready — %d chunks indexed", count)
    yield


app = FastAPI(
    title="LegalDev",
    version="0.1.0",
    description="Asistente RAG de normativa legal para developers en España",
    lifespan=lifespan,
)

app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_methods=["GET", "POST"],
    allow_headers=["Content-Type", "Authorization"],
)

Instrumentator().instrument(app).expose(app)


def _analyze_handler(input: QuestionnaireInput, request: Request) -> RAGResponse:
    return run_pipeline(input, request.app.state)


def _normativas_handler(request: Request) -> dict:
    try:
        result = request.app.state.vectorstore._collection.get(include=["metadatas"])
        sources = sorted({m["source"] for m in result["metadatas"] if m.get("source")})
        return {"normativas": sources, "total": len(sources)}
    except Exception:
        return {"normativas": [], "total": 0}


@app.get("/")
def root():
    return {
        "name": "LegalDev",
        "version": "0.1.0",
        "description": "Asistente RAG de normativa legal para developers en España",
    }


@app.get("/health")
def health(request: Request):
    try:
        docs_indexed = request.app.state.vectorstore._collection.count()
    except Exception:
        docs_indexed = -1
    return {"status": "ok", "docs_indexed": docs_indexed}


@app.get("/normativas")
def normativas(request: Request):
    return _normativas_handler(request)


v1 = APIRouter(prefix="/v1", tags=["v1"])


@v1.post("/analyze", response_model=RAGResponse)
@limiter.limit(settings.rate_limit)
def analyze_v1(input: QuestionnaireInput, request: Request):
    return _analyze_handler(input, request)


app.include_router(v1)
