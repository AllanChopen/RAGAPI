const API_BASE = "/api/v1";
export const DEMO_PROJECT_ID = "frontend-demo";

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
  let repository = null;
  let documents = null;

  if (repoUrl) {
    const response = await fetch(`${API_BASE}/repositories/ingest`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        project_id: DEMO_PROJECT_ID,
        repository_url: repoUrl,
      }),
    });
    repository = await readJsonResponse(response);
  }

  if (Array.isArray(files) && files.length > 0) {
    const form = new FormData();
    form.append("project_id", DEMO_PROJECT_ID);
    files.forEach((file) => form.append("files", file));

    const response = await fetch(`${API_BASE}/documents/ingest`, {
      method: "POST",
      body: form,
    });
    documents = await readJsonResponse(response);
  }

  return { repository, documents };
}

export async function askQuestion({ query, history, debug }) {
  const response = await fetch(`${API_BASE}/query`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      project_id: DEMO_PROJECT_ID,
      question: query,
      conversation_history: history || [],
      debug: Boolean(debug),
    }),
  });

  return readJsonResponse(response);
}

export async function resetProjectIndex() {
  const response = await fetch(`${API_BASE}/projects/${encodeURIComponent(DEMO_PROJECT_ID)}/index`, {
    method: "DELETE",
  });

  return readJsonResponse(response);
}
