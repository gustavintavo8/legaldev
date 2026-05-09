import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request, APIRouter
from fastapi.middleware.cors import CORSMiddleware
from langchain_huggingface import HuggingFaceEmbeddings
from langchain_chroma import Chroma
from langchain_groq import ChatGroq
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded

from app.config import settings
from app.models import QuestionnaireInput, RAGResponse
from app.rag import run_pipeline

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

EMBEDDING_MODEL = "all-MiniLM-L6-v2"
CHROMA_COLLECTION = "legaldev"

limiter = Limiter(key_func=get_remote_address)


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
    )
    logger.info("LegalDev is ready")
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


def _analyze_handler(input: QuestionnaireInput, request: Request) -> RAGResponse:
    return run_pipeline(input, request.app.state)


def _normativas_handler(request: Request) -> dict:
    try:
        result = request.app.state.vectorstore._collection.get(include=["metadatas"])
        sources = sorted({m["source"] for m in result["metadatas"] if m.get("source")})
        return {"normativas": sources, "total": len(sources)}
    except Exception:
        return {"normativas": [], "total": 0}


# Root and health stay unversioned (Railway health checks, discovery)
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
    except AttributeError:
        docs_indexed = -1
    return {"status": "ok", "docs_indexed": docs_indexed}


@app.get("/normativas")
def normativas(request: Request):
    return _normativas_handler(request)


# Legacy route (kept for backwards compat, hidden from docs)
@app.post("/analyze", response_model=RAGResponse, include_in_schema=False)
@limiter.limit(settings.rate_limit)
def analyze(input: QuestionnaireInput, request: Request):
    return _analyze_handler(input, request)


# v1 router — canonical API
v1 = APIRouter(prefix="/v1", tags=["v1"])


@v1.post("/analyze", response_model=RAGResponse)
@limiter.limit(settings.rate_limit)
def analyze_v1(input: QuestionnaireInput, request: Request):
    return _analyze_handler(input, request)


app.include_router(v1)
