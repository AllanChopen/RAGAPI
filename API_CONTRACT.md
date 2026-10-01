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
- filtrado por proyecto, ramas y documento;
- listado, ingesta y filtrado de commits Git;
- construcción del prompt;
- llamada al proveedor de IA;
- trazabilidad de fuentes;
- comparación de ramas mediante Git diff;
- registro y métricas de consultas.

## Flujo recomendado

1. `POST /repositories/branches`
2. `POST /repositories/ingest`
3. `POST /documents/ingest` cuando existan documentos o SQL
4. `POST /repositories/commits` y `POST /repositories/commits/ingest` cuando se necesite consultar versiones históricas
5. `GET /projects/{project_id}/sources` para conocer las opciones disponibles
6. `POST /query`
7. `POST /compare` cuando se necesite comparar ramas
8. `GET /metrics` para observabilidad del RAG

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

Una nueva ingesta de ramas del mismo `project_id + repositorio` reemplaza sus ramas y el manifiesto, pero conserva los commits indexados explícitamente.

### Listar e indexar commits

`POST /repositories/commits` recibe `repository_url`, `branch` opcional y `limit` (1 a 100, por defecto 20). Devuelve `repository`, `branch` y `commits` con `sha`, `message` y `authored_at`.

```json
{
  "repository_url": "https://github.com/organizacion/proyecto",
  "branch": "main",
  "limit": 20
}
```

`POST /repositories/commits/ingest` recibe `project_id`, `repository_url` y `commits` (entre 1 y 10 SHA completos o prefijos únicos de 7 a 40 caracteres). Devuelve el SHA completo, mensaje, archivos procesados y chunks creados por cada commit. Indexa el snapshot de código, el mensaje, la lista de archivos modificados y fragmentos del diff frente al primer padre. Un commit raíz se compara con un árbol vacío. Reindexar un commit reemplaza solo sus chunks; conserva ramas, otros commits y documentos. Para buscar commits antiguos se descarga el historial completo del repositorio.

```json
{
  "project_id": "123",
  "repository_url": "https://github.com/organizacion/proyecto",
  "commits": ["abcdef1234567890"]
}
```

## 3. Indexar documentos y SQL

### `POST /documents/ingest`

Tipo de solicitud: `multipart/form-data`.

Campos:

```text
project_id = 123
files = requerimientos.pdf
files = especificacion.docx
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
Los archivos Word `.docx` se procesan como documentación: se extrae el texto de los párrafos y tablas del cuerpo. El formato antiguo `.doc` no está incluido.

## 4. Listar fuentes indexadas del proyecto

### `GET /projects/{project_id}/sources`

Devuelve los repositorios, ramas con contenido, commits indexados explícitamente y documentos del proyecto. Un proyecto sin índice devuelve listas vacías y `total_chunks: 0`.

```json
{
  "project_id": "123",
  "repositories": [
    {
      "name": "proyecto",
      "chunks": 263,
      "branches": [
        { "name": "main", "commit": "abc123...", "chunks": 250 }
      ],
      "commits": [
        { "sha": "def456...", "message": "Agregar módulo", "chunks": 12 }
      ]
    }
  ],
  "documents": [
    { "name": "esquema.sql", "artifact_type": "database", "chunks": 8 }
  ],
  "total_chunks": 271
}
```

`chunks` del repositorio incluye su chunk técnico de metadata y los commits indexados. Usa `documents[].name` como valor exacto del campo `document`, o `repositories[].commits[].sha` para `commit`. El nombre del documento distingue mayúsculas y minúsculas.

## 5. Consultar el RAG

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

Solicitud restringida a un documento:

```json
{
  "project_id": "123",
  "question": "¿Qué tablas define el esquema?",
  "document": "esquema.sql"
}
```

Si se omiten `document`, `branches` y `commit`, se consultan las ramas actuales y los documentos del proyecto; los snapshots históricos explícitos se excluyen para no mezclar versiones. Con `document`, solo se recuperan chunks de ese documento: no se consultan repositorios ni otros documentos. `document` y `branches` son filtros alternativos; enviarlos juntos devuelve `422`. Un documento no indexado para ese proyecto devuelve `409`.

Solicitud restringida a un commit:

```json
{
  "project_id": "123",
  "question": "¿Qué cambió en este commit?",
  "commit": "def4567",
  "repository": "proyecto"
}
```

`commit` acepta SHA completo o prefijo único de 7 a 40 caracteres y se resuelve al SHA completo indexado. `repository` es opcional y desambigua proyectos con varios repositorios. `commit` no se combina con `branches` ni `document` (`422`). Un SHA ausente o ambiguo devuelve `409`. La recuperación se limita al repositorio y SHA resueltos; se excluyen documentos y otras versiones. Sin filtro de commit, las consultas habituales excluyen los snapshots históricos para evitar mezclar versiones. Un commit punta ya indexado por rama puede consultarse por SHA, aunque el mensaje y el diff requieren la ingesta explícita del commit.

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

## 6. Comparar ramas

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

## 7. Estado

### `GET /health`

Valida:

- conexión a base de datos;
- extensión pgvector y tabla de chunks;
- configuración del proveedor de embeddings;
- configuración del proveedor generativo.

## 8. Métricas

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

## 9. Eliminar índice de un proyecto

### `DELETE /projects/{project_id}/index`

Elimina únicamente los chunks vectoriales de ese `project_id`. No elimina el proyecto del backend ni su historial de consultas.

## Errores principales

| HTTP | Significado |
|---|---|
| `400` | Solicitud inválida o archivo no soportado |
| `409` | El proyecto, documento, commit o las ramas requeridas todavía no están indexados; SHA ambiguo |
| `422` | Filtros incompatibles o solicitud que no cumple el esquema |
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
