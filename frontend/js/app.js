import { ingestSources, askQuestion, resetProjectIndex } from "./api.js";
import {
  addSource,
  addTurn,
  clearConversation,
  clearState,
  hasSources,
  loadState,
  recentHistoryForRequest,
  saveState,
  state,
} from "./state.js";
import { dom, renderAll, renderChat, renderDebug, renderChatAvailability, setLoading, setNotice } from "./ui.js";

function refresh() {
  renderAll({
    sources: state.sources,
    history: state.history,
    isLoading: state.loading,
    lastResponse: state.lastResponse,
    debugEnabled: dom.debugToggle.checked,
  });
}

function setAppLoading(isLoading) {
  state.loading = isLoading;
  setLoading(isLoading);
  renderChatAvailability(hasSources(), isLoading);
}

function validateIngestInput(repoUrl, files) {
  if (!repoUrl && files.length === 0) {
    throw new Error("Ingresa una URL de repositorio o selecciona uno o más archivos.");
  }
}

function registerIngestedSources(data, repoUrl) {
  if (data.documents) {
    data.documents.documents.forEach((document) => {
      addSource({
        type: "uploaded",
        label: document.name,
        value: document.name,
        chunks: document.chunks_created,
      });
    });
  }

  if (data.repository) {
    addSource({
      type: "repo",
      label: data.repository.repository,
      value: data.repository.repository,
      chunks: data.repository.total_chunks,
    });
  } else if (repoUrl) {
    throw new Error("No se pudo ingestar el repositorio. Revisa la URL, permisos o conexión.");
  }
}

async function handleIngest(event) {
  event.preventDefault();

  const repoUrl = dom.repoUrl.value.trim();
  const files = Array.from(dom.filesInput.files || []);

  try {
    validateIngestInput(repoUrl, files);
    setAppLoading(true);
    setNotice("muted", "Ingestando fuentes e identificando ramas...");

    const data = await ingestSources({ repoUrl, files });
    registerIngestedSources(data, repoUrl);

    dom.filesInput.value = "";
    const documentChunks = data.documents?.total_chunks || 0;
    const repositoryChunks = data.repository?.total_chunks || 0;
    setNotice(
      "success",
      `Ingesta completada. Documentos: ${documentChunks} chunks. Repositorio: ${repositoryChunks} chunks.`
    );
    clearConversation();
    refresh();
  } catch (error) {
    setNotice("error", error.message || String(error));
  } finally {
    setAppLoading(false);
  }
}

async function handleAsk(event) {
  event.preventDefault();

  const query = dom.messageInput.value.trim();
  if (!query || !hasSources()) return;

  try {
    const historyForRequest = recentHistoryForRequest();
    dom.messageInput.value = "";
    setAppLoading(true);
    renderChat(state.history, query);

    const data = await askQuestion({
      query,
      history: historyForRequest,
      debug: dom.debugToggle.checked,
    });

    state.lastResponse = data;
    addTurn(query, data.answer || "Sin respuesta.");
    state.history[state.history.length - 1].citations = data.sources || [];
    saveState();
    refresh();
  } catch (error) {
    addTurn(query, `Error: ${error.message || String(error)}`);
    refresh();
  } finally {
    setAppLoading(false);
  }
}

async function handleReset() {
  const confirmed = window.confirm(
    "Esto limpiará la sesión de prueba y eliminará el índice RAG del proyecto frontend-demo. ¿Continuar?"
  );

  if (!confirmed) return;

  try {
    setAppLoading(true);
    const data = await resetProjectIndex();
    clearState();
    setNotice("success", `Sesión reiniciada. Chunks eliminados: ${data.deleted_chunks || 0}.`);
    refresh();
  } catch (error) {
    setNotice("error", error.message || String(error));
  } finally {
    setAppLoading(false);
  }
}

function boot() {
  dom.year.textContent = new Date().getFullYear();
  loadState();
  refresh();

  dom.ingestForm.addEventListener("submit", handleIngest);
  dom.chatForm.addEventListener("submit", handleAsk);
  dom.resetButton.addEventListener("click", handleReset);
  dom.debugToggle.addEventListener("change", () => renderDebug(state.lastResponse, dom.debugToggle.checked));
}

boot();
