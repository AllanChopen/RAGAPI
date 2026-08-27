# RAG API para proyectos de software

API FastAPI orientada exclusivamente a la capa RAG del proyecto final: ingesta, chunking, embeddings, almacenamiento vectorial, recuperación, generación con LLM, trazabilidad de fuentes y comparación de ramas Git.

## Responsabilidad de esta API

El backend general es responsable de usuarios, autenticación, registro de proyectos, permisos y lógica de negocio. Esta API recibe un `project_id` externo y lo utiliza únicamente para aislar el conocimiento indexado.

Flujo principal:

1. El backend registra/selecciona un proyecto.
2. Consulta las ramas de un repositorio.
3. Indexa las ramas requeridas.
4. Indexa documentación y scripts SQL.
5. Formula preguntas indicando `project_id` y opcionalmente ramas.
6. El RAG recupera chunks semánticamente relevantes.
7. El LLM responde usando exclusivamente el contexto recuperado.
8. La API devuelve respuesta y fuentes estructuradas.

## API pública v1

Swagger: `http://127.0.0.1:8000/docs`

| Método | Endpoint | Uso |
|---|---|---|
| POST | `/api/v1/repositories/branches` | Obtener ramas remotas y rama por defecto |
| POST | `/api/v1/repositories/ingest` | Indexar una o varias ramas |
| POST | `/api/v1/documents/ingest` | Indexar documentos, diccionarios y SQL |
| POST | `/api/v1/query` | Consultar un proyecto mediante RAG |
| POST | `/api/v1/compare` | Comparar dos ramas con Git diff + RAG |
| DELETE | `/api/v1/projects/{project_id}/index` | Eliminar el contexto vectorial de un proyecto |
| GET | `/api/v1/health` | Estado del RAG, DB, pgvector y proveedores |
| GET | `/api/v1/metrics` | Cantidad de consultas, errores y tiempo promedio |

Los endpoints de prueba y boilerplate de versiones anteriores fueron retirados para mantener un contrato RAG único y claro. El contrato para el equipo backend está documentado en `API_CONTRACT.md`, la cobertura de la propuesta en `COMPLIANCE.md` y el flujo de validación en `TESTING.md`.

## Proveedores de IA

La generación está desacoplada del RAG mediante `LLMService`.

`LLM_PROVIDER` acepta:

- `huggingface`
- `openai`
- `anthropic`
- `openai_compatible`

El proveedor de embeddings es independiente mediante `EMBEDDING_PROVIDER`. Por ejemplo, puedes usar Claude para generación y conservar Hugging Face u OpenAI para embeddings sin modificar el flujo RAG.

`EMBEDDING_PROVIDER` acepta:

- `huggingface` (por defecto)
- `openai`

El modelo de embeddings por defecto es `sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2`. Sus vectores semánticos de 384 dimensiones se completan con ceros hasta `EMBEDDING_DIMENSIONS=1536`, conservando la similitud coseno y evitando una migración destructiva de la tabla pgvector existente.

## Configuración

Copia `.env.example` a `.env` y configura las credenciales necesarias.

Configuración actual por defecto:

```env
LLM_PROVIDER=huggingface
LLM_MAX_OUTPUT_TOKENS=1600
HF_API_TOKEN=...
HF_MODEL_NAME=Qwen/Qwen2.5-Coder-32B-Instruct

EMBEDDING_PROVIDER=huggingface
EMBEDDING_MODEL_NAME=sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2
EMBEDDING_DIMENSIONS=1536
```

Para OpenAI:

```env
LLM_PROVIDER=openai
OPENAI_API_KEY=...
OPENAI_MODEL_NAME=...
```

Para Anthropic:

```env
LLM_PROVIDER=anthropic
ANTHROPIC_API_KEY=...
ANTHROPIC_MODEL_NAME=...
```

Para otro proveedor compatible con Chat Completions de OpenAI:

```env
LLM_PROVIDER=openai_compatible
OPENAI_COMPATIBLE_BASE_URL=https://proveedor.example/v1
OPENAI_COMPATIBLE_API_KEY=...
OPENAI_COMPATIBLE_MODEL_NAME=...
```

## Requisitos previos

- Python 3.11 o superior.
- Git instalado en el servidor.
- PostgreSQL con la extensión `pgvector` disponible.
- Acceso al proveedor de embeddings y al proveedor generativo configurados.

## Instalación

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

Windows PowerShell:

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

## Ejecutar

```bash
uvicorn RAGAPI:app --reload
```

Swagger:

```text
http://127.0.0.1:8000/docs
```

Frontend interno de pruebas:

```text
http://127.0.0.1:8000/
```

El frontend utiliza los endpoints v1 con el `project_id` de prueba `frontend-demo`.

## Ejemplos

### Listar ramas

```json
POST /api/v1/repositories/branches
{
  "repository_url": "https://github.com/dashed/git-chain"
}
```

### Indexar repositorio

```json
POST /api/v1/repositories/ingest
{
  "project_id": "proyecto-1",
  "repository_url": "https://github.com/dashed/git-chain",
  "branches": ["master", "fix-merge-commit-info"]
}
```

Si `branches` es `null` u omitido se indexan todas las ramas remotas encontradas.

### Consultar

```json
POST /api/v1/query
{
  "project_id": "proyecto-1",
  "question": "¿Dónde se implementa el manejo de merge commits?",
  "branches": ["fix-merge-commit-info"]
}
```

### Comparar ramas

```json
POST /api/v1/compare
{
  "project_id": "proyecto-1",
  "repository_url": "https://github.com/dashed/git-chain",
  "branch_a": "master",
  "branch_b": "fix-merge-commit-info",
  "question": "¿Qué cambió en el manejo de merge commits?"
}
```

`/compare` obtiene el listado real de archivos modificados con Git y utiliza RAG para explicar el contenido de los cambios. Ambas ramas deben haberse indexado previamente.

## Tipos de contenido

La ingesta reconoce código fuente, Markdown, PDF, JSON, CSV, XLSX, Draw.io/XML, YAML, Dockerfiles y scripts `.sql`. Los chunks almacenan metadata de trazabilidad como:

- `project_id`
- `source_type`
- `repository` o `document`
- `branch`
- `commit`
- `file_path`
- líneas o página/hoja cuando aplica
- `artifact_type`

## Reindexación

Los chunks antiguos generados con el embedding determinístico previo no deben mezclarse con el nuevo índice semántico. Los endpoints v1 están aislados por `project_id`, y cada reingesta reemplaza el contenido del mismo repositorio o documento dentro de ese proyecto.

Para eliminar por completo el índice de un proyecto:

```text
DELETE /api/v1/projects/{project_id}/index
```
