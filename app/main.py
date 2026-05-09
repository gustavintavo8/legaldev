import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from langchain_huggingface import HuggingFaceEmbeddings
from langchain_chroma import Chroma
from langchain_groq import ChatGroq

from app.config import settings
from app.models import QuestionnaireInput, RAGResponse
from app.rag import run_pipeline

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

EMBEDDING_MODEL = "paraphrase-multilingual-MiniLM-L12-v2"
CHROMA_COLLECTION = "legaldev"


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
    )
    logger.info("LegalDev is ready")
    yield


app = FastAPI(
    title="LegalDev",
    version="0.1.0",
    description="Asistente RAG de normativa legal para developers en España",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


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


@app.post("/analyze", response_model=RAGResponse)
def analyze(input: QuestionnaireInput, request: Request):
    return run_pipeline(input, request.app.state)
