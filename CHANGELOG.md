# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

## [0.1.0] - 2026-05-09

### Added
- RAG pipeline over 16 Spanish/EU legal documents (RGPD, EU AI Act, NIS2, LOPDGDD, LSSI, ENS, LPI, guías AEPD, Código Ético CCII)
- `POST /analyze` endpoint: structured questionnaire → applicable regulations with technical implications
- `GET /health` endpoint with live document count from ChromaDB
- MMR retrieval to avoid redundant chunks
- Page-level citations in retrieved chunks
- Rate limiting on `/analyze` (configurable, default 10 req/min)
- Configurable CORS origins via `ALLOWED_ORIGINS` env var
- Groq API timeout via `GROQ_TIMEOUT` env var
- Standalone `ingest.py` script to build the vector store from PDFs
- Docker + docker-compose support
- Railway deployment via pre-built `chroma_db/` baked into the Docker image
- Mandatory legal disclaimer on every response
