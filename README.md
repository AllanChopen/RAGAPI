# RAG FastAPI

This project uses `RAGAPI.py` as the FastAPI entrypoint, similar to a `.NET` `Program.cs` file.

## Structure

- `RAGAPI.py`: application bootstrap
- `app/controllers`: request handlers
- `app/models`: SQLAlchemy models
- `app/services`: business logic
- `app/views`: response shaping
- `app/schemas`: request and response contracts
- `app/core`: settings and database session setup

## Run locally

1. Update `.env` with either `DATABASE_URL` (recommended, e.g. Supabase PostgreSQL) or the MySQL fallback values.
2. Set `HF_API_TOKEN` and optionally `HF_MODEL_URL` for Hugging Face inference tests.
3. Install dependencies from `requirements.txt`.
4. Start the API with `uvicorn RAGAPI:app --reload`.
5. Open `/docs` for Swagger UI.

## Hugging Face test endpoint

- Method: `POST`
- Path: `/api/hf/test`

Example request body:

```json
{
	"prompt": "Explain what RAG is in one sentence.",
	"max_new_tokens": 120,
	"temperature": 0.2
}
```

## Git source endpoint (local or remote)

- Method: `POST`
- Path: `/api/git/scan`

Local repository example:

```json
{
	"local_path": "C:/Users/allan/Documents/Python/RAG",
	"max_files": 100,
	"include_extensions": [".py", ".md", ".xml"]
}
```

Note: local_path must be an initialized Git repository directory.

## Vector storage endpoint (Supabase pgvector)

- Method: `GET`
- Path: `/api/vector/health`
- Purpose: verify `vector` extension and `context_chunks` table availability.

- Method: `POST`
- Path: `/api/vector/test-upsert`
- Purpose: insert a test chunk with embedding.

Example request body (`embedding` must match `EMBEDDING_DIMENSIONS`, default 1536):

```json
{
	"source": "manual-test",
	"content": "Sample context chunk",
	"embedding": [0.0, 0.0, 0.0],
	"metadata_json": {
		"type": "test"
	}
}
```

For the example above, set `EMBEDDING_DIMENSIONS=3` in `.env` before calling `/api/vector/test-upsert`.

- Method: `POST`
- Path: `/api/vector/search`
- Purpose: retrieve top-k semantically similar chunks from `context_chunks`.

Example request body:

```json
{
	"query": "how flask handles request context",
	"top_k": 5,
	"source": "flask"
}
```

Remote repository example (GitHub/GitLab):

```json
{
	"repo_url": "https://github.com/owner/repo.git",
	"branch": "main",
	"max_files": 100,
	"include_extensions": [".py", ".ts", ".md"]
}
```

## Git ingest endpoint (scan + vector store)

- Method: `POST`
- Path: `/api/git/ingest`
- Purpose: clone/open repository, chunk file content, generate embeddings, and store chunks in `context_chunks`.

Example request body:

```json
{
	"repo_url": "https://github.com/octocat/Hello-World.git",
	"branch": "master",
	"max_files": 50,
	"include_extensions": [".md", ".py", ".ts"],
	"chunk_size": 1200,
	"chunk_overlap": 150,
	"max_chunks_per_file": 20
}
```

## RAG question endpoint (retrieval + generation)

- Method: `POST`
- Path: `/api/rag/ask`
- Purpose: retrieve top-k chunks from `context_chunks` and generate an answer with Hugging Face.

Example request body:

```json
{
	"query": "How does Flask manage request context?",
	"source": "flask",
	"top_k": 5,
	"max_new_tokens": 300,
	"temperature": 0.2
}
```

## RAG streaming endpoint (SSE)

- Method: `POST`
- Path: `/api/rag/ask/stream`
- Purpose: same retrieval flow as `/api/rag/ask`, but emits streaming events (`meta`, `token`, `done`).

Example request body:

```json
{
	"query": "How does Flask manage request context?",
	"source": "flask",
	"top_k": 5,
	"max_new_tokens": 300,
	"temperature": 0.2
}
```

## Simple user loop (no manual JSON)

- UI: `GET /api/chat`
- Step 1: connect repo using `POST /api/chat/setup?repo_url=...&branch=...`
- Step 2: ask questions using `POST /api/chat/ask?chat_id=...&query=...`
- Step 3 (optional): ingest dictionary using `POST /api/chat/dictionary/ingest?file_path=...&dictionary_name=...`
- Step 4 (optional): trace field usage using `POST /api/chat/trace-field?field_name=...&dictionary_name=...`

This flow is designed so users only paste a repository once and then ask natural-language questions.

Supported artifact ingestion in `/api/chat/setup` and `/api/git/ingest`:

- Architecture: `.drawio`, Draw.io `.xml`, Mermaid `.mmd/.mermaid`
- Data dictionaries: `.xlsx`, `.csv`, `.json`
- Technical documentation: `.md`, `.pdf`
- Infrastructure: `Dockerfile`, `docker-compose.yml/.yaml`, Kubernetes manifests `.yaml/.yml`

## Cross traceability (Data Dictionary -> Code)

- Ingest data dictionary (Excel): `POST /api/trace/dictionary/ingest`
- Trace field usage in code: `POST /api/trace/field-usage`

Dictionary ingest body:

```json
{
	"file_path": "C:/path/to/dictionary.xlsx",
	"dictionary_name": "DiccionarioClientes",
	"sheet_name": "Campos"
}
```

Field usage body:

```json
{
	"field_name": "customer_id",
	"dictionary_name": "DiccionarioClientes",
	"top_k": 20
}
```

Each trace match includes explicit source citation: file path + line range.

## Reliability Rules

- Citation of sources: RAG answers now append a `Fuentes` section with file line ranges and tab when available.
- Context memory: `/api/chat/ask` keeps session turn history and injects recent turns into retrieval generation.
- Knowledge isolation: RAG prompt is strict and only uses loaded context; when evidence is missing, it returns:
  `No hay evidencia suficiente en los documentos cargados.`