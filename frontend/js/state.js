const STORAGE_KEY = "rag-software-architect-state-v1";

export const state = {
  sources: [],
  history: [],
  loading: false,
  lastResponse: null,
};

export function loadState() {
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    if (!raw) return;

    const parsed = JSON.parse(raw);
    state.sources = Array.isArray(parsed.sources) ? parsed.sources : [];
    state.history = Array.isArray(parsed.history) ? parsed.history : [];
    state.lastResponse = parsed.lastResponse || null;
  } catch (_error) {
    clearState();
  }
}

export function saveState() {
  const payload = {
    sources: state.sources,
    history: state.history.slice(-10),
    lastResponse: state.lastResponse,
  };
  localStorage.setItem(STORAGE_KEY, JSON.stringify(payload));
}

export function clearState() {
  state.sources = [];
  state.history = [];
  state.loading = false;
  state.lastResponse = null;
  localStorage.removeItem(STORAGE_KEY);
}

export function hasSources() {
  return state.sources.length > 0;
}

export function addSource(source) {
  const normalized = {
    id: source.id || `${source.type}:${source.value || source.label}`,
    type: source.type,
    label: source.label,
    value: source.value,
    chunks: Number(source.chunks || 0),
    createdAt: new Date().toISOString(),
  };

  const exists = state.sources.some((item) => item.id === normalized.id);
  if (!exists) {
    state.sources.push(normalized);
    saveState();
  }
}

export function addTurn(user, assistant) {
  state.history.push({ user, assistant });
  state.history = state.history.slice(-10);
  saveState();
}

export function clearConversation() {
  state.history = [];
  state.lastResponse = null;
  saveState();
}

export function sourceValues() {
  return state.sources.map((source) => source.value).filter(Boolean);
}

export function recentHistoryForRequest() {
  return state.history.slice(-6).map((turn) => ({
    user: String(turn.user || ""),
    assistant: String(turn.assistant || ""),
  }));
}
