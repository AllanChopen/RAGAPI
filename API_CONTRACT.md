# Contrato de integración - RAG API v1

URL base de desarrollo:

```text
http://127.0.0.1:8000/api/v1
```

Swagger:

```text
http://127.0.0.1:8000/docs
```

## Responsabilidad del backend consumidor

El backend general administra usuarios, autenticación, proyectos, permisos, interfaz y lógica de negocio. El backend entrega a esta API un `project_id` estable que funciona como espacio de nombres del conocimiento RAG.

La API RAG administra exclusivamente:

- extracción de Git y documentos;
- chunking;
- embeddings;
- almacenamiento y recuperación vectorial;
- filtrado por proyecto y ramas;
- construcción del prompt;
- llamada al proveedor de IA;
- trazabilidad de fuentes;
- comparación de ramas mediante Git diff;
- registro y métricas de consultas.

## Flujo recomendado

1. `POST /repositories/branches`
2. `POST /repositories/ingest`
3. `POST /documents/ingest` cuando existan documentos o SQL
4. `POST /query`
5. `POST /compare` cuando se necesite comparar ramas
6. `GET /metrics` para observabilidad del RAG

## 1. Listar ramas

### `POST /repositories/branches`

Solicitud:

```json
{
  "repository_url": "https://github.com/organizacion/proyecto"
}
```

Respuesta:

```json
{
  "repository": "proyecto",
  "default_branch": "main",
  "branches": [
    {
      "name": "main",
      "commit": "abc123...",
      "default": true
    },
    {
      "name": "develop",
      "commit": "def456...",
      "default": false
    }
  ]
}
```

## 2. Indexar repositorio

### `POST /repositories/ingest`

Solicitud recomendada:

```json
{
  "project_id": "123",
  "repository_url": "https://github.com/organizacion/proyecto",
  "branches": ["main", "develop"]
}
```

Si `branches` se omite o se envía como `null`, se indexan todas las ramas remotas detectadas. Para integración con backend se recomienda enviarlas explícitamente.

Respuesta:

```json
{
  "project_id": "123",
  "repository": "proyecto",
  "branches": [
    {
      "name": "main",
      "commit": "abc123...",
      "files_processed": 80,
      "chunks_created": 250
    }
  ],
  "total_files": 80,
  "total_chunks": 251
}
```

`total_chunks` incluye un chunk técnico de metadata del repositorio que registra las ramas remotas detectadas, sus commits punta y cuáles fueron indexadas.

Una nueva ingesta del mismo `project_id + repositorio` reemplaza el índice anterior de ese repositorio.

## 3. Indexar documentos y SQL

### `POST /documents/ingest`

Tipo de solicitud: `multipart/form-data`.

Campos:

```text
project_id = 123
files = requerimientos.pdf
files = esquema.sql
files = diccionario.xlsx
```

Respuesta:

```json
{
  "project_id": "123",
  "documents": [
    {
      "name": "esquema.sql",
      "artifact_type": "database",
      "chunks_created": 8
    }
  ],
  "total_chunks": 8
}
```

Una nueva ingesta de un documento con el mismo nombre dentro del mismo `project_id` reemplaza sus chunks anteriores.

## 4. Consultar el RAG

### `POST /query`

Solicitud general:

```json
{
  "project_id": "123",
  "question": "¿Dónde se implementa el inicio de sesión?"
}
```

Solicitud restringida a ramas:

```json
{
  "project_id": "123",
  "question": "¿Cómo funciona el inicio de sesión?",
  "branches": ["develop"]
}
```

Respuesta:

```json
{
  "project_id": "123",
  "question": "¿Cómo funciona el inicio de sesión?",
  "answer": "La autenticación se realiza ... [S1]",
  "sources": [
    {
      "chunk_id": 120,
      "source_type": "repository",
      "source": "project:123:repository:proyecto",
      "repository": "proyecto",
      "document": null,
      "branch": "develop",
      "commit": "def456...",
      "file_path": "app/services/auth.py",
      "line_start": 20,
      "line_end": 65,
      "page": null,
      "tab": null,
      "artifact_type": "code",
      "score": 0.82
    }
  ],
  "context_chunks_used": 1,
  "provider": "huggingface",
  "model": "...",
  "response_time_ms": 930.5,
  "debug_matches": null
}
```

El consumidor debe utilizar `sources` como evidencia estructurada. Los identificadores `[S1]`, `[S2]`, etc. usados dentro de `answer` corresponden al orden del arreglo `sources`.

## 5. Comparar ramas

### `POST /compare`

Las dos ramas deben haber sido indexadas previamente para el proyecto.

Solicitud:

```json
{
  "project_id": "123",
  "repository_url": "https://github.com/organizacion/proyecto",
  "branch_a": "main",
  "branch_b": "develop",
  "question": "¿Qué cambió en el proceso de autenticación?"
}
```

Respuesta:

```json
{
  "project_id": "123",
  "repository": "proyecto",
  "branch_a": "main",
  "branch_b": "develop",
  "question": "¿Qué cambió en el proceso de autenticación?",
  "answer": "...",
  "changes": [
    {
      "status": "M",
      "path": "app/services/auth.py",
      "previous_path": null
    }
  ],
  "sources": [],
  "context_chunks_used": 0,
  "provider": "...",
  "model": "...",
  "response_time_ms": 0,
  "debug_matches": null
}
```

`changes` proviene del Git diff real entre ambas referencias. La recuperación del RAG se restringe a los archivos reportados por ese diff y a las dos ramas solicitadas.

## 6. Estado

### `GET /health`

Valida:

- conexión a base de datos;
- extensión pgvector y tabla de chunks;
- configuración del proveedor de embeddings;
- configuración del proveedor generativo.

## 7. Métricas

### `GET /metrics`

Respuesta:

```json
{
  "total_queries": 30,
  "successful_queries": 28,
  "failed_queries": 2,
  "average_response_time_ms": 812.44
}
```

## 8. Eliminar índice de un proyecto

### `DELETE /projects/{project_id}/index`

Elimina únicamente los chunks vectoriales de ese `project_id`. No elimina el proyecto del backend ni su historial de consultas.

## Errores principales

| HTTP | Significado |
|---|---|
| `400` | Solicitud inválida, rama desconocida o archivo no soportado |
| `409` | El proyecto o las ramas requeridas todavía no están indexados |
| `502` | Error accediendo a Git, embeddings o proveedor de IA |
| `503` | Base de datos / almacenamiento RAG no disponible |

## Proveedores de IA

El backend consumidor no cambia su integración cuando cambia el modelo. El proveedor generativo se configura en el servidor RAG mediante `LLM_PROVIDER`.

Proveedores implementados:

- `huggingface`
- `openai`
- `anthropic`
- `openai_compatible`

Los embeddings se configuran independientemente con `EMBEDDING_PROVIDER` (`huggingface` u `openai`).
