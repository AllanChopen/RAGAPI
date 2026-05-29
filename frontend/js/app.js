import { ingestSources, askQuestion, resetUploadedSession } from "./api.js";
import {
  addSource,
  addTurn,
  clearConversation,
  clearState,
  hasSources,
  loadState,
  recentHistoryForRequest,
  saveState,
  sourceValues,
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

function registerIngestedSources(data, repoUrl, fileCount) {
  if (data.uploaded_source) {
    addSource({
      type: "uploaded",
      label: `${fileCount} archivo(s) cargado(s)`,
      value: data.uploaded_source,
      chunks: data.uploaded_chunks,
    });
  }

  if (data.repo_name) {
    addSource({
      type: "repo",
      label: data.repo_name,
      value: data.repo_name,
      chunks: data.repo_chunks,
    });
  } else if (repoUrl && !data.repo_name) {
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
    setNotice("muted", "Ingestando fuentes. Esto puede tardar según el tamaño del repo o archivos...");

    const data = await ingestSources({ repoUrl, files });
    registerIngestedSources(data, repoUrl, files.length);

    dom.filesInput.value = "";
    setNotice(
      "success",
      `Ingesta completada. Archivos: ${data.uploaded_chunks || 0} chunks. Repo: ${data.repo_chunks || 0} chunks.`
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
      sources: sourceValues(),
      history: historyForRequest,
      debug: dom.debugToggle.checked,
    });

    state.lastResponse = data;
    addTurn(query, data.answer || "Sin respuesta.");
    state.history[state.history.length - 1].citations = data.citations || [];
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
    "Esto limpiará la sesión visual y eliminará chunks subidos con source uploaded:%. Los repositorios ya indexados pueden permanecer en la base de datos. ¿Continuar?"
  );

  if (!confirmed) return;

  try {
    setAppLoading(true);
    const data = await resetUploadedSession();
    clearState();
    setNotice("success", `Sesión reiniciada. Chunks subidos eliminados: ${data.deleted_uploaded_chunks || 0}.`);
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
