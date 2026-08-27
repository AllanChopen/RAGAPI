# Pruebas de aceptación de RAG API

Estas pruebas validan el contrato público de la API y los puntos principales del MVP: ingesta, ramas, embeddings, recuperación, respuesta con fuentes, SQL, comparación y métricas.

## 1. Preparar el entorno

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
```

Configura `DATABASE_URL` y las credenciales del proveedor de IA elegido. Con la configuración por defecto, `HF_API_TOKEN` se utiliza tanto para generación Hugging Face como para embeddings.

Levanta el servicio:

```bash
uvicorn RAGAPI:app --reload
```

Swagger:

```text
http://127.0.0.1:8000/docs
```

## 2. Health

```bash
curl http://127.0.0.1:8000/api/v1/health
```

Esperado: `status` igual a `healthy` si DB, pgvector, embeddings y LLM están configurados correctamente.

## 3. Listar ramas de un repositorio

```bash
curl -X POST http://127.0.0.1:8000/api/v1/repositories/branches \
  -H "Content-Type: application/json" \
  -d '{"repository_url":"https://github.com/dashed/git-chain"}'
```

Verifica que la respuesta incluya `repository`, `default_branch` y `branches` con nombre y commit.

## 4. Indexar ramas

```bash
curl -X POST http://127.0.0.1:8000/api/v1/repositories/ingest \
  -H "Content-Type: application/json" \
  -d '{
    "project_id":"rag-test",
    "repository_url":"https://github.com/dashed/git-chain",
    "branches":["master","fix-merge-commit-info"]
  }'
```

Esperado: ambas ramas aparecen en `branches`, cada una con `commit`, `files_processed` y `chunks_created`.

## 5. Preguntar qué ramas se indexaron

```bash
curl -X POST http://127.0.0.1:8000/api/v1/query \
  -H "Content-Type: application/json" \
  -d '{
    "project_id":"rag-test",
    "question":"¿Qué ramas existen en el repositorio indexado y qué commit punta tiene cada una?"
  }'
```

Esperado: la respuesta identifica las ramas indexadas y `sources` contiene evidencia de tipo `repository_metadata`.

## 6. Consulta restringida a una rama

```bash
curl -X POST http://127.0.0.1:8000/api/v1/query \
  -H "Content-Type: application/json" \
  -d '{
    "project_id":"rag-test",
    "question":"¿Cómo funciona get_merge_commit_info?",
    "branches":["fix-merge-commit-info"]
  }'
```

Verifica que las fuentes de código pertenezcan a `fix-merge-commit-info` y muestren archivo, líneas y commit.

Repite con:

```text
En master, ¿cómo funciona el manejo de merge commits?
```

pasando `"branches":["master"]`.

## 7. Comparar dos ramas

```bash
curl -X POST http://127.0.0.1:8000/api/v1/compare \
  -H "Content-Type: application/json" \
  -d '{
    "project_id":"rag-test",
    "repository_url":"https://github.com/dashed/git-chain",
    "branch_a":"master",
    "branch_b":"fix-merge-commit-info",
    "question":"¿Qué cambió en el manejo de merge commits?"
  }'
```

Esperado:

- `changes` contiene el Git diff real entre ambas ramas.
- La explicación diferencia claramente cada rama.
- Las fuentes pertenecen a los archivos modificados y muestran su rama/commit.

## 8. Indexar un script SQL

Desde Swagger usa `POST /api/v1/documents/ingest` con:

```text
project_id = rag-test
files = TestFiles/rag_schema_test.sql
```

También puedes cargar `TestFiles/blackjack_arquitectura.drawio` y `TestFiles/blackjack_diccionario_datos_rag.xlsx` para validar arquitectura y diccionario de datos.

## 9. Preguntas de base de datos

Ejecuta en `/api/v1/query`:

```text
¿Qué tablas define el script SQL cargado?
```

```text
¿Qué campos tiene la tabla customers?
```

```text
¿Cómo se relacionan las tablas users y roles?
```

```text
¿Qué función modifica el inventario y qué parámetros recibe?
```

Las respuestas deben incluir `sources` apuntando a `rag_schema_test.sql`.

## 10. Preguntas de documentación y arquitectura

Si cargaste los archivos de prueba, pregunta:

```text
¿Qué componentes aparecen en la arquitectura cargada?
```

```text
¿Qué campos están documentados en el diccionario de datos?
```

La respuesta debe estar respaldada por los documentos correspondientes y no por conocimiento externo del modelo.

## 11. Sugerencia de refactorización

Pregunta sobre un método recuperable del repositorio:

```text
Analiza get_merge_commit_info y propón una refactorización. Separa claramente lo observado en el código de tu propuesta de mejora.
```

El RAG debe citar el código observado y presentar la mejora como propuesta, sin afirmar que ya existe en el repositorio.

## 12. Métricas

```bash
curl http://127.0.0.1:8000/api/v1/metrics
```

Después de varias consultas, valida que aumente `total_queries` y que exista un tiempo promedio de respuesta.

## 13. Aislamiento por proyecto

Indexa contenido utilizando otro `project_id`, por ejemplo `rag-test-2`, y realiza la misma consulta. Las fuentes de un proyecto no deben aparecer en el otro.

## 14. Borrar índice

```bash
curl -X DELETE http://127.0.0.1:8000/api/v1/projects/rag-test/index
```

Después intenta consultar de nuevo `rag-test`. Esperado: HTTP `409` indicando que el proyecto no tiene contexto RAG indexado.

## 15. Cambiar proveedor generativo

Sin cambiar código, modifica `.env`.

OpenAI:

```env
LLM_PROVIDER=openai
OPENAI_API_KEY=...
OPENAI_MODEL_NAME=...
```

Anthropic:

```env
LLM_PROVIDER=anthropic
ANTHROPIC_API_KEY=...
ANTHROPIC_MODEL_NAME=...
```

Proveedor OpenAI-compatible:

```env
LLM_PROVIDER=openai_compatible
OPENAI_COMPATIBLE_BASE_URL=https://proveedor.example/v1
OPENAI_COMPATIBLE_API_KEY=...
OPENAI_COMPATIBLE_MODEL_NAME=...
```

Reinicia la API y consulta `/api/v1/health` para comprobar la configuración activa.

## Criterios de aprobación

El RAG se considera funcionalmente aprobado cuando:

1. Aísla recuperación por `project_id`.
2. Permite seleccionar una o varias ramas.
3. Recupera código/documentación/SQL relevante mediante embeddings semánticos.
4. Responde usando únicamente contexto recuperado o declara evidencia insuficiente.
5. Devuelve fuentes estructuradas con archivo/documento, rama y commit cuando aplica.
6. Compara ramas a partir de Git diff real y evidencia RAG.
7. Registra consultas y métricas básicas.
8. El proveedor generativo puede cambiarse por configuración sin modificar el flujo RAG.

## Verificaciones de Swagger después de instalar dependencias

Si actualizaste una versión anterior del proyecto, ejecuta:

```bash
pip install -r requirements.txt --upgrade
```

Después reinicia FastAPI y realiza una recarga fuerte de `http://127.0.0.1:8000/docs`.

### Health

Ejecuta `GET /api/v1/health`. El endpoint debe responder HTTP `200` cuando PostgreSQL está disponible. El campo `status` puede ser `healthy` o `degraded`: `degraded` es válido cuando el proveedor de embeddings o el LLM todavía no tienen credenciales configuradas. Si PostgreSQL no está disponible, el endpoint responde HTTP `503` con un mensaje controlado en lugar de un error `500`.

### Carga de documentos desde Swagger

En `POST /api/v1/documents/ingest`, presiona **Try it out**. Deben aparecer:

- `project_id`: campo de texto.
- `files`: selector para uno o varios archivos.

Selecciona uno o varios archivos y ejecuta la solicitud. Swagger los envía como `multipart/form-data`; no debes escribir rutas locales de archivos manualmente.
