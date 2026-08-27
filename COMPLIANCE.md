# Cobertura de la Propuesta de Proyecto Final

Este repositorio implementa el **componente RAG/API** de la plataforma. No pretende reemplazar el backend general, el frontend definitivo, la infraestructura ni el trabajo de QA.

## Cobertura del componente RAG

| Requerimiento de la propuesta | Implementación en esta API |
|---|---|
| Conectar/cargar repositorio Git | `POST /api/v1/repositories/branches` y `POST /api/v1/repositories/ingest` |
| Seleccionar rama | `branches` en la ingesta y en las consultas |
| Leer código de distintas ramas | Ingesta independiente por branch con `branch` y `commit` en metadata |
| Cargar documentación | `POST /api/v1/documents/ingest` |
| Procesar SQL/esquemas | Parser/clasificación `.sql` con `artifact_type=database` |
| Dividir contenido | Chunking configurable por variables `RAG_*` |
| Generar embeddings | `EmbeddingService` con Hugging Face u OpenAI |
| Almacenar embeddings | PostgreSQL + pgvector en `context_chunks` |
| Recuperar información | Búsqueda vectorial + reranking lexical, aislada por `project_id` |
| Enviar contexto a un LLM | `RAGService` construye contexto/prompt y `LLMService` abstrae proveedor |
| Responder en lenguaje natural | `POST /api/v1/query` |
| Mostrar fuentes | `sources` estructurado con archivo/documento, rama, commit, líneas/página y score |
| Comparar ramas | `POST /api/v1/compare` usa Git diff real + retrieval limitado a archivos modificados |
| Sugerencias/refactorización | Prompt obliga a separar evidencia observada de propuesta textual |
| Registrar consultas | Tabla `rag_query_logs` |
| Cantidad/tiempo/errores de consultas | `GET /api/v1/metrics` |
| Estado de RAG/DB/vector/modelo | `GET /api/v1/health` |
| Ramas y commits consultables | Manifest de repositorio indexado como `repository_metadata` |
| Cambiar modelo/proveedor | `LLM_PROVIDER`: Hugging Face, OpenAI, Anthropic u OpenAI-compatible |

## Preguntas mínimas cubiertas por el RAG

La arquitectura soporta consultas de:

- ubicación e implementación de funcionalidades en código;
- funciones/clases y dependencias;
- tablas, campos, relaciones y procedimientos presentes en SQL o documentación;
- requerimientos y funcionalidad descrita en documentos;
- ramas existentes y commits punta;
- diferencias entre dos ramas;
- archivos modificados según Git diff;
- propuestas de refactorización fundamentadas en código recuperado;
- comparación entre documentación y código cuando ambos fueron indexados.

## Responsabilidades externas a esta API

### Backend general

- registro y administración de proyectos;
- usuarios, autenticación y permisos;
- persistencia de la lógica de negocio general;
- decidir qué `project_id`, repositorio, ramas y documentos se envían al RAG.

### Frontend definitivo

- interfaz de administración;
- chat final;
- selección visual de proyectos y ramas;
- presentación final de las fuentes.

El `frontend/` incluido en este repositorio es únicamente una interfaz interna para probar el RAG.

### Arquitectura e infraestructura

- servidor/VM;
- Docker y estado de contenedores;
- CPU, RAM y disco;
- disponibilidad del servidor;
- dashboard de infraestructura;
- redes y seguridad de despliegue.

La API sí entrega `/health` y `/metrics` para que la capa de observabilidad consuma estado y métricas propias del RAG.

### QA y evaluación

- banco formal de preguntas y respuestas esperadas;
- medición de precisión/relevancia;
- pruebas funcionales finales;
- documentación de defectos y resultados de evaluación.

`TESTING.md` contiene un banco inicial de aceptación técnica para este componente.
