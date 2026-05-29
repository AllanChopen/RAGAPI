## Manual de instalación y ejecución local

Este proyecto es una API RAG desarrollada con **FastAPI**, orientada a centralizar conocimiento técnico desde repositorios de código, documentos, diagramas Draw.io, archivos Excel, Markdown, PDF y otros artefactos técnicos.
La aplicación incluye una interfaz web tipo chat para cargar fuentes de información y realizar preguntas usando recuperación aumentada por generación.

---

## 1. Requisitos previos

Antes de ejecutar el proyecto, asegúrate de tener instalado:

* Python 3.10 o superior.
* Git.
* PostgreSQL con extensión `pgvector`, o una base de datos Supabase PostgreSQL.
* Una API Key de Hugging Face.
* Navegador web actualizado.

También se recomienda usar un entorno virtual de Python para evitar conflictos con dependencias globales.

---

## 2. Clonar o descargar el proyecto

Clona el repositorio o descarga el código fuente en tu equipo.

```bash
git clone https://github.com/AllanChopen/RAGAPI
cd RAGAPI
```

Si el proyecto fue entregado como archivo `.zip`, descomprímelo y entra a la carpeta raíz del proyecto:

```bash
cd RAGAPI
```

La raíz del proyecto debe contener archivos como:

```text
RAGAPI.py
requirements.txt
.env.example
app/
frontend/
TestFiles/
README.md
```

---

## 3. Crear entorno virtual

En Windows:

```bash
python -m venv venv
venv\Scripts\activate
```

En macOS o Linux:

```bash
python3 -m venv venv
source venv/bin/activate
```

Cuando el entorno virtual esté activo, deberías ver algo parecido a esto en la terminal:

```text
(venv)
```

---

## 4. Instalar dependencias

Instala las dependencias del proyecto usando:

```bash
pip install -r requirements.txt
```

El archivo `requirements.txt` incluye las librerías necesarias para:

* FastAPI.
* Uvicorn.
* SQLAlchemy.
* PostgreSQL.
* pgvector.
* Procesamiento de Excel.
* Procesamiento de PDF.
* Lectura de XML / Draw.io.
* Clonación de repositorios Git.
* Integración con Hugging Face.

---

## 5. Configurar variables de entorno

Copia el archivo `.env.example` y crea un archivo `.env` en la raíz del proyecto.

En Windows:

```bash
copy .env.example .env
```

En macOS o Linux:

```bash
cp .env.example .env
```

Luego abre el archivo `.env` y configura tus valores reales.

Ejemplo:

```env
APP_NAME=RAG API
API_PREFIX=/api

DATABASE_URL=postgresql://USUARIO:CONTRASENA@HOST:PUERTO/postgres

HF_API_TOKEN=hf_tu_token_de_huggingface
HF_MODEL_URL=https://router.huggingface.co/v1/chat/completions
HF_MODEL_NAME=Qwen/Qwen2.5-Coder-32B-Instruct

EMBEDDING_DIMENSIONS=1536
```

---

## 6. Configurar base de datos PostgreSQL / Supabase

El proyecto utiliza una tabla llamada `context_chunks` para guardar fragmentos de información, metadatos y embeddings.

Se recomienda usar PostgreSQL con la extensión `pgvector`.

Si usas Supabase:

1. Crea un proyecto en Supabase.
2. Copia la cadena de conexión PostgreSQL.
3. Colócala en la variable `DATABASE_URL` del archivo `.env`.
4. Verifica que la extensión `vector` esté disponible.

El proyecto intenta crear la extensión automáticamente al iniciar:

```sql
CREATE EXTENSION IF NOT EXISTS vector;
```

Si tu usuario de base de datos no tiene permisos para crear extensiones, habilita `vector` manualmente desde Supabase o desde tu administrador de base de datos.

---

## 7. Ejecutar el servidor

Desde la raíz del proyecto, ejecuta:

```bash
uvicorn RAGAPI:app --reload
```

Si todo está correcto, deberías ver una salida similar a:

```text
Uvicorn running on http://127.0.0.1:8000
```

---

## 8. Abrir la interfaz web

Abre el navegador y entra a:

```text
http://127.0.0.1:8000/
```

Desde esta interfaz puedes:

* Ingresar un enlace de repositorio Git.
* Cargar archivos como Excel, Draw.io, PDF, Markdown, CSV, JSON o XML.
* Ingestar las fuentes cargadas.
* Realizar preguntas en formato chat.
* Ver fuentes utilizadas por la respuesta.
* Consultar trazabilidad entre documentación, código y diccionarios de datos.

---

## 9. Abrir Swagger UI

La documentación interactiva de la API está disponible en:

```text
http://127.0.0.1:8000/docs
```

Desde Swagger puedes probar endpoints como:

* `POST /api/rag/ingest`
* `POST /api/rag/ask/upload`
* `POST /api/rag/ask`
* `POST /api/git/ingest`
* `POST /api/vector/search`
* `POST /api/trace/dictionary/ingest`
* `POST /api/trace/field-usage`

---

## 10. Flujo recomendado de uso desde la interfaz

### Paso 1: cargar conocimiento

Primero debes proporcionar información al sistema. Puedes usar una o varias fuentes:

* URL de un repositorio GitHub o GitLab.
* Archivo `.drawio` o `.xml` con arquitectura.
* Archivo `.xlsx` con diccionario de datos.
* Documentación `.md` o `.pdf`.
* Archivos `.csv`, `.json`, `.yaml`, `.yml`, `Dockerfile`, entre otros.

### Paso 2: ingestar fuentes

Después de seleccionar las fuentes, presiona el botón para ingestar información.
El sistema procesará los documentos y guardará fragmentos consultables en la base vectorial.

### Paso 3: hacer preguntas

Cuando existan fuentes cargadas, puedes realizar preguntas como:

```text
¿Qué hace este repositorio?
```

```text
Explícame la arquitectura del sistema.
```

```text
¿En qué archivos se usa el campo customer_id definido en el diccionario de datos?
```

```text
¿Qué impacto tendría cambiar esta función?
```

---

## 11. Archivos de prueba incluidos

El proyecto incluye una carpeta llamada:

```text
TestFiles/
```

Dentro de esta carpeta pueden existir archivos de prueba como:

```text
diccionario_datos.xlsx
diccionario_datos_APIBanca.xlsx
arquitectura_rag.drawio
arquitectura_APIBanca.drawio
```

Estos archivos sirven para validar la ingesta de:

* Diccionarios de datos en Excel.
* Diagramas de arquitectura en Draw.io.
* Relaciones entre documentación técnica y código fuente.

---

## 12. Ejemplo de prueba rápida

Ejecuta el servidor:

```bash
uvicorn RAGAPI:app --reload
```

Abre:

```text
http://127.0.0.1:8000/
```

Carga una fuente, por ejemplo:

* Un repositorio Git.
* Un archivo Excel desde `TestFiles/`.
* Un archivo Draw.io desde `TestFiles/`.

Luego pregunta:

```text
¿Qué información contienen las fuentes cargadas?
```

Otra pregunta recomendada:

```text
Explícame la arquitectura del sistema según el diagrama cargado.
```

Y para validar trazabilidad:

```text
¿En qué archivos de código se usa el campo definido en el diccionario de datos?
```

---

## 13. Reiniciar la sesión de carga

La interfaz incluye una opción para reiniciar la sesión actual.
Esto permite limpiar fuentes temporales cargadas y comenzar una nueva prueba sin mezclar contexto anterior.

También puedes usar el endpoint:

```text
POST /api/rag/reset_session
```

---

## 14. Consideraciones importantes

* El modelo responde priorizando únicamente las fuentes cargadas.
* Si no existe evidencia suficiente en los documentos cargados, el sistema debe responder:

```text
No hay evidencia suficiente en los documentos cargados.
```

* Las respuestas deben incluir fuentes o referencias cuando exista información recuperada.
* Para mejores resultados, carga documentos relacionados entre sí, por ejemplo:

  * Repositorio de código.
  * Diagrama de arquitectura.
  * Diccionario de datos.
  * Documentación técnica.

---

## 15. Problemas comunes

### Error de conexión a base de datos

Verifica que `DATABASE_URL` esté correctamente configurado en `.env`.

También confirma que la base de datos esté activa y acepte conexiones externas.

---

### Error relacionado con `vector`

Si aparece un error relacionado con `vector`, `pgvector` o la extensión `vector`, habilita la extensión en PostgreSQL:

```sql
CREATE EXTENSION IF NOT EXISTS vector;
```

---

### Error de Hugging Face

Si el modelo no responde, revisa:

* Que `HF_API_TOKEN` sea válido.
* Que `HF_MODEL_URL` esté configurado.
* Que `HF_MODEL_NAME` exista y esté disponible.
* Que tengas conexión a internet.

---

### La IA responde que no hay evidencia suficiente

Esto puede ocurrir cuando:

* No se han cargado fuentes.
* La pregunta no está relacionada con los documentos cargados.
* El documento cargado no contiene información suficiente.
* La fuente no fue correctamente ingestada.

Para corregirlo, carga al menos una fuente válida y vuelve a realizar la pregunta.

---

## 16. Comando principal de ejecución

El comando principal recomendado para levantar el proyecto en local es:

```bash
uvicorn RAGAPI:app --reload
```

URL principal:

```text
http://127.0.0.1:8000/
```

Swagger UI:

```text
http://127.0.0.1:8000/docs
```
