import { ingestSources, askQuestion, listProjectSources, resetProjectIndex } from "./api.js";
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
    selectedDocument: state.selectedDocument,
    selectedCommit: state.selectedCommit,
    selectedRepository: state.selectedRepository,
  });
}

async function refreshIndexedSources() {
  const inventory = await listProjectSources();
  state.sources = [
    ...inventory.repositories.map((repository) => ({
      id: `repo:${repository.name}`,
      type: "repo",
      label: repository.name,
      value: repository.name,
      chunks: repository.chunks,
      commits: repository.commits || [],
    })),
    ...inventory.documents.map((document) => ({
      id: `uploaded:${document.name}`,
      type: "uploaded",
      label: document.name,
      value: document.name,
      chunks: document.chunks,
    })),
  ];
  if (
    state.selectedDocument &&
    !inventory.documents.some((document) => document.name === state.selectedDocument)
  ) {
    state.selectedDocument = null;
    clearConversation();
  }
  if (
    state.selectedCommit &&
    !inventory.repositories.some((repository) =>
      repository.name === state.selectedRepository &&
      repository.commits.some((commit) => commit.sha === state.selectedCommit)
    )
  ) {
    state.selectedCommit = null;
    state.selectedRepository = null;
    clearConversation();
  }
  saveState();
  refresh();
}

function setAppLoading(isLoading) {
  state.loading = isLoading;
  setLoading(isLoading);
  renderChatAvailability(hasSources(), isLoading);
}

function validateIngestInput(repoUrl, files, commits) {
  if (!repoUrl && files.length === 0) {
    throw new Error("Ingresa una URL de repositorio o selecciona uno o más archivos.");
  }
  if (commits.length && !repoUrl) {
    throw new Error("Ingresa la URL del repositorio al indicar commits.");
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

  if (data.repository || data.commitIndex) {
    const indexed = data.repository || data.commitIndex;
    addSource({
      type: "repo",
      label: indexed.repository,
      value: indexed.repository,
      chunks: indexed.total_chunks,
    });
  } else if (repoUrl) {
    throw new Error("No se pudo ingestar el repositorio. Revisa la URL, permisos o conexión.");
  }
}

async function handleIngest(event) {
  event.preventDefault();

  const repoUrl = dom.repoUrl.value.trim();
  const files = Array.from(dom.filesInput.files || []);
  const commits = dom.commitShas.value.split(/[\s,]+/).map((sha) => sha.trim()).filter(Boolean);

  try {
    validateIngestInput(repoUrl, files, commits);
    setAppLoading(true);
    setNotice("muted", "Ingestando fuentes...");

    const data = await ingestSources({ repoUrl, files, commits });
    registerIngestedSources(data, repoUrl);
    await refreshIndexedSources();

    dom.filesInput.value = "";
    dom.commitShas.value = "";
    const documentChunks = data.documents?.total_chunks || 0;
    const repositoryChunks = data.repository?.total_chunks || data.commitIndex?.total_chunks || 0;
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
      document: state.selectedDocument,
      commit: state.selectedCommit,
      repository: state.selectedRepository,
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
  refreshIndexedSources().catch((error) => {
    state.sources = [];
    state.selectedDocument = null;
    state.selectedCommit = null;
    state.selectedRepository = null;
    saveState();
    refresh();
    setNotice("error", `No se pudieron cargar las fuentes indexadas: ${error.message || String(error)}`);
  });

  dom.ingestForm.addEventListener("submit", handleIngest);
  dom.chatForm.addEventListener("submit", handleAsk);
  dom.resetButton.addEventListener("click", handleReset);
  dom.sourceScope.addEventListener("change", () => {
    state.selectedDocument = dom.sourceScope.value || null;
    if (state.selectedDocument) {
      state.selectedCommit = null;
      state.selectedRepository = null;
    }
    clearConversation();
    refresh();
  });
  dom.commitScope.addEventListener("change", () => {
    const [repository, commit] = dom.commitScope.value
      ? JSON.parse(dom.commitScope.value)
      : [null, null];
    state.selectedRepository = repository;
    state.selectedCommit = commit;
    if (commit) state.selectedDocument = null;
    clearConversation();
    refresh();
  });
  dom.debugToggle.addEventListener("change", () => renderDebug(state.lastResponse, dom.debugToggle.checked));
}

boot();
