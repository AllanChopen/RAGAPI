const RAG_API_BASE = "/api/rag";

async function readJsonResponse(response) {
  let payload = null;

  try {
    payload = await response.json();
  } catch (_error) {
    payload = null;
  }

  if (!response.ok) {
    const detail = payload?.detail || payload?.message || `HTTP ${response.status}`;
    throw new Error(detail);
  }

  return payload;
}

export async function ingestSources({ repoUrl, files }) {
  const form = new FormData();

  if (repoUrl) {
    form.append("repo_url", repoUrl);
  }

  Array.from(files || []).forEach((file) => {
    form.append("files", file);
  });

  form.append("keep_uploaded", "true");

  const response = await fetch(`${RAG_API_BASE}/ingest`, {
    method: "POST",
    body: form,
  });

  return readJsonResponse(response);
}

export async function askQuestion({ query, sources, history, debug }) {
  const form = new FormData();

  form.append("query", query);
  form.append("top_k", "10");
  form.append("max_new_tokens", "500");
  form.append("temperature", "0.2");
  form.append("combine_sources", "false");
  form.append("conversation_history", JSON.stringify(history || []));

  if (Array.isArray(sources) && sources.length > 0) {
    form.append("sources", sources.join(","));
  }

  if (debug) {
    form.append("debug", "true");
  }

  const response = await fetch(`${RAG_API_BASE}/ask/upload`, {
    method: "POST",
    body: form,
  });

  return readJsonResponse(response);
}

export async function resetUploadedSession() {
  const response = await fetch(`${RAG_API_BASE}/reset_session`, {
    method: "POST",
  });

  return readJsonResponse(response);
}
