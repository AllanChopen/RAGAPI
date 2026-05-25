from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import HTMLResponse
import httpx
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.schemas.git_schema import GitIngestRequest
from app.schemas.rag_schema import RAGAskRequest, RAGAskResponse
from app.schemas.trace_schema import DataDictionaryIngestRequest, FieldUsageTraceRequest
from app.services.chat_session_service import ChatSessionService
from app.services.git_service import GitService
from app.services.rag_service import RAGService
from app.services.trace_service import TraceService


router = APIRouter(prefix="/chat", tags=["chat"])


@router.get("", response_class=HTMLResponse, summary="Simple chat UI")
def chat_ui() -> str:
    return """
<!doctype html>
<html lang=\"es\">
<head>
  <meta charset=\"utf-8\" />
  <meta name=\"viewport\" content=\"width=device-width, initial-scale=1\" />
  <title>RAG Chat</title>
  <style>
    body { font-family: Segoe UI, Arial, sans-serif; margin: 0; background: #f4f6fb; color: #172133; }
    .wrap { max-width: 980px; margin: 40px auto; padding: 0 16px; }
    .card { background: #fff; border-radius: 14px; box-shadow: 0 8px 30px rgba(23,33,51,.08); padding: 18px; margin-bottom: 14px; }
    h1 { margin: 0 0 10px; }
    h2 { margin: 0 0 10px; font-size: 18px; }
    .row { display: flex; gap: 10px; flex-wrap: wrap; }
    input, textarea, button { border-radius: 10px; border: 1px solid #d8dfec; padding: 10px 12px; font-size: 14px; }
    input, textarea { flex: 1; min-width: 220px; }
    textarea { width: 100%; min-height: 100px; resize: vertical; }
    button { background: #0d6efd; border-color: #0d6efd; color: white; cursor: pointer; }
    button:disabled { opacity: .5; cursor: not-allowed; }
    .muted { color: #5c6a82; font-size: 13px; }
    .answer { white-space: pre-wrap; line-height: 1.5; }
    .mono { font-family: Consolas, Menlo, monospace; font-size: 12px; white-space: pre-wrap; background: #f6f8fc; border: 1px solid #e5ebf6; border-radius: 10px; padding: 10px; }
    .ok { color: #0a7a3b; }
    .err { color: #a12727; }
  </style>
</head>
<body>
  <div class=\"wrap\">
    <div class=\"card\">
      <h1>Repo to Chat</h1>
      <p class=\"muted\">Paso 1: pega URL GitHub/GitLab y conecta. Paso 2: pregunta en lenguaje natural.</p>
      <p class=\"muted\">La ingesta cubre arquitectura (.drawio/.xml y Mermaid), diccionarios (.xlsx/.csv/.json), docs (.md/.pdf) e infraestructura (Docker/K8s).</p>
      <div class=\"row\">
        <input id=\"repo\" placeholder=\"https://github.com/owner/repo.git\" />
        <input id=\"branch\" placeholder=\"main (opcional)\" />
        <button id=\"connect\">Conectar repo</button>
      </div>
      <p id=\"status\" class=\"muted\"></p>
    </div>

    <div class=\"card\">
      <div class=\"row\">
        <input id=\"question\" placeholder=\"Haz tu pregunta sobre el repo\" disabled />
        <button id=\"ask\" disabled>Preguntar</button>
      </div>
      <p class=\"muted\">Respuesta</p>
      <div id=\"answer\" class=\"answer muted\">Conecta un repo para empezar.</div>
    </div>

    <div class=\"card\">
      <h2>Trazabilidad Cruzada</h2>
      <p class=\"muted\">1) Ingiere diccionario de datos. 2) Consulta uso de campo en código.</p>
      <div class=\"row\">
        <input id=\"dictPath\" placeholder=\"C:/ruta/diccionario.xlsx\" />
        <input id=\"dictName\" placeholder=\"Nombre de diccionario (ej: DiccionarioClientes)\" />
        <input id=\"dictSheet\" placeholder=\"Pestaña (opcional)\" />
        <button id=\"ingestDict\">Ingerir diccionario</button>
      </div>
      <div class=\"row\">
        <input id=\"fieldName\" placeholder=\"Campo a rastrear (ej: customer_id)\" />
        <button id=\"traceField\">Trazar campo</button>
      </div>
      <p id=\"traceStatus\" class=\"muted\"></p>
      <div id=\"traceResult\" class=\"mono muted\">Aquí verás archivo + línea + pestaña.</div>
    </div>
  </div>

  <script>
    let chatId = "";

    const repo = document.getElementById("repo");
    const branch = document.getElementById("branch");
    const connectBtn = document.getElementById("connect");
    const askBtn = document.getElementById("ask");
    const question = document.getElementById("question");
    const statusEl = document.getElementById("status");
    const answerEl = document.getElementById("answer");
    const dictPath = document.getElementById("dictPath");
    const dictName = document.getElementById("dictName");
    const dictSheet = document.getElementById("dictSheet");
    const ingestDictBtn = document.getElementById("ingestDict");
    const traceFieldBtn = document.getElementById("traceField");
    const fieldName = document.getElementById("fieldName");
    const traceStatus = document.getElementById("traceStatus");
    const traceResult = document.getElementById("traceResult");

    connectBtn.onclick = async () => {
      const repoUrl = repo.value.trim();
      const branchValue = branch.value.trim();
      if (!repoUrl) {
        statusEl.className = "err";
        statusEl.textContent = "Ingresa una URL de repo.";
        return;
      }

      connectBtn.disabled = true;
      statusEl.className = "muted";
      statusEl.textContent = "Ingestando repositorio...";

      const params = new URLSearchParams({ repo_url: repoUrl });
      if (branchValue) params.set("branch", branchValue);

      try {
        const res = await fetch(`/api/chat/setup?${params.toString()}`, { method: "POST" });
        const data = await res.json();
        if (!res.ok) throw new Error(data.detail || "Error de ingesta");

        chatId = data.chat_id;
        question.disabled = false;
        askBtn.disabled = false;
        statusEl.className = "ok";
        statusEl.textContent = `Listo: ${data.repo_name}. Archivos: ${data.files_processed}, chunks: ${data.chunks_inserted}`;
        answerEl.textContent = "Repo conectado. Haz tu pregunta.";
      } catch (err) {
        statusEl.className = "err";
        statusEl.textContent = String(err.message || err);
      } finally {
        connectBtn.disabled = false;
      }
    };

    askBtn.onclick = async () => {
      const q = question.value.trim();
      if (!chatId || !q) return;

      askBtn.disabled = true;
      answerEl.className = "answer muted";
      answerEl.textContent = "Pensando...";

      try {
        const params = new URLSearchParams({ chat_id: chatId, query: q });
        const res = await fetch(`/api/chat/ask?${params.toString()}`, { method: "POST" });
        const data = await res.json();
        if (!res.ok) throw new Error(data.detail || "Error al responder");

        answerEl.className = "answer";
        answerEl.textContent = data.answer || "Sin respuesta";
      } catch (err) {
        answerEl.className = "answer err";
        answerEl.textContent = String(err.message || err);
      } finally {
        askBtn.disabled = false;
      }
    };

    ingestDictBtn.onclick = async () => {
      const filePath = dictPath.value.trim();
      const name = dictName.value.trim();
      const sheet = dictSheet.value.trim();
      if (!filePath || !name) {
        traceStatus.className = "err";
        traceStatus.textContent = "Ingresa file path y dictionary name.";
        return;
      }

      ingestDictBtn.disabled = true;
      traceStatus.className = "muted";
      traceStatus.textContent = "Ingeriendo diccionario...";
      try {
        const params = new URLSearchParams({ file_path: filePath, dictionary_name: name });
        if (sheet) params.set("sheet_name", sheet);
        const res = await fetch(`/api/chat/dictionary/ingest?${params.toString()}`, { method: "POST" });
        const data = await res.json();
        if (!res.ok) throw new Error(data.detail || "Error ingestando diccionario");
        traceStatus.className = "ok";
        traceStatus.textContent = `Diccionario ingestado: ${data.dictionary_name}. Campos: ${data.fields_ingested}`;
      } catch (err) {
        traceStatus.className = "err";
        traceStatus.textContent = String(err.message || err);
      } finally {
        ingestDictBtn.disabled = false;
      }
    };

    traceFieldBtn.onclick = async () => {
      const field = fieldName.value.trim();
      const name = dictName.value.trim();
      if (!field || !name) {
        traceStatus.className = "err";
        traceStatus.textContent = "Ingresa field name y dictionary name.";
        return;
      }

      traceFieldBtn.disabled = true;
      traceStatus.className = "muted";
      traceStatus.textContent = "Buscando trazabilidad...";
      traceResult.className = "mono muted";
      traceResult.textContent = "Procesando...";

      try {
        const params = new URLSearchParams({ field_name: field, dictionary_name: name, top_k: "20" });
        const res = await fetch(`/api/chat/trace-field?${params.toString()}`, { method: "POST" });
        const data = await res.json();
        if (!res.ok) throw new Error(data.detail || "Error en trazabilidad");

        const header = [
          `Campo: ${data.field_name}`,
          `Diccionario: ${data.dictionary_name}`,
          `Pestaña/row origen: ${data.dictionary_tab || 'N/A'} / ${data.dictionary_row || 'N/A'}`,
          `Definicion: ${data.dictionary_definition || 'N/A'}`,
          "",
          "Usos encontrados:",
        ];

        const lines = (data.matches || []).map((m, idx) => {
          return `${idx + 1}. ${m.file_path}:${m.line_start}-${m.line_end} (sim=${Number(m.similarity || 0).toFixed(4)})`;
        });

        traceResult.className = "mono";
        traceResult.textContent = [...header, ...lines].join("\n");
        traceStatus.className = "ok";
        traceStatus.textContent = `Listo. Matches: ${(data.matches || []).length}`;
      } catch (err) {
        traceStatus.className = "err";
        traceStatus.textContent = String(err.message || err);
        traceResult.className = "mono err";
        traceResult.textContent = String(err.message || err);
      } finally {
        traceFieldBtn.disabled = false;
      }
    };
  </script>
</body>
</html>
"""


@router.post("/setup", summary="Connect a repository and ingest context")
def setup_chat(
    repo_url: str | None = Query(default=None),
    local_path: str | None = Query(default=None),
    branch: str | None = Query(default=None),
    db: Session = Depends(get_db),
):
    if not repo_url and not local_path:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Provide repo_url or local_path")

    payload = GitIngestRequest(
        repo_url=repo_url,
        local_path=local_path,
        branch=branch,
        max_files=120,
      include_extensions=[
        ".py",
        ".ts",
        ".js",
        ".md",
        ".pdf",
        ".json",
        ".csv",
        ".xlsx",
        ".yaml",
        ".yml",
        ".xml",
        ".drawio",
        ".mmd",
        ".mermaid",
      ],
        chunk_size=1200,
        chunk_overlap=150,
        max_chunks_per_file=20,
    )

    try:
        result = GitService.ingest_repository(payload, db)
        session = ChatSessionService.create_session(source=result.repo_name, repo_name=result.repo_name)
        return {
            "chat_id": session.id,
            "repo_name": result.repo_name,
            "files_processed": result.files_processed,
            "chunks_inserted": result.chunks_inserted,
        }
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(exc)) from exc
    except SQLAlchemyError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Database unavailable while ingesting repository",
        ) from exc


@router.post("/ask", response_model=RAGAskResponse, summary="Ask a question using connected repo context")
def ask_chat(
    chat_id: str = Query(...),
    query: str = Query(...),
    top_k: int = Query(default=5, ge=1, le=20),
    max_new_tokens: int = Query(default=300, ge=32, le=1200),
    temperature: float = Query(default=0.2, ge=0.0, le=1.5),
    db: Session = Depends(get_db),
) -> RAGAskResponse:
    session = ChatSessionService.get_session(chat_id)
    if not session:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Chat session not found")

    payload = RAGAskRequest(
        query=query,
        source=session.source,
        top_k=top_k,
        max_new_tokens=max_new_tokens,
        temperature=temperature,
        conversation_history=session.history,
    )

    try:
        response = RAGService.ask(db, payload)
        ChatSessionService.add_turn(chat_id, query, response.answer)
        return response
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    except httpx.HTTPStatusError as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Hugging Face API error: {exc.response.text}",
        ) from exc
    except httpx.HTTPError as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Unable to connect to Hugging Face API: {str(exc)}",
        ) from exc
    except SQLAlchemyError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Database unavailable while running retrieval",
        ) from exc


@router.post("/dictionary/ingest", summary="Ingest data dictionary for traceability")
def chat_ingest_dictionary(
    file_path: str = Query(...),
    dictionary_name: str = Query(...),
    sheet_name: str | None = Query(default=None),
    db: Session = Depends(get_db),
) -> dict:
    payload = DataDictionaryIngestRequest(
        file_path=file_path,
        dictionary_name=dictionary_name,
        sheet_name=sheet_name,
    )
    try:
        result = TraceService.ingest_data_dictionary(db, payload)
        return result.model_dump()
    except FileNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    except SQLAlchemyError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Database unavailable while ingesting data dictionary",
        ) from exc


@router.post("/trace-field", summary="Trace field usage from dictionary to code")
def chat_trace_field(
    field_name: str = Query(...),
    dictionary_name: str = Query(...),
    top_k: int = Query(default=20, ge=1, le=200),
    db: Session = Depends(get_db),
) -> dict:
    payload = FieldUsageTraceRequest(field_name=field_name, dictionary_name=dictionary_name, top_k=top_k)
    try:
        result = TraceService.trace_field_usage(db, payload)
        return result.model_dump()
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except SQLAlchemyError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Database unavailable while tracing field usage",
        ) from exc
