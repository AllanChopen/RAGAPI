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

export async function ingestSources({ repoUrl, files, commits = [] }) {
  let repository = null;
  let documents = null;
  let commitIndex = null;

  if (repoUrl) {
    const response = await fetch(
      `${API_BASE}/repositories/${commits.length ? "commits/ingest" : "ingest"}`,
      {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          project_id: DEMO_PROJECT_ID,
          repository_url: repoUrl,
          ...(commits.length ? { commits } : {}),
        }),
      }
    );
    const result = await readJsonResponse(response);
    if (commits.length) commitIndex = result;
    else repository = result;
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

  return { repository, documents, commitIndex };
}

export async function listProjectSources() {
  const response = await fetch(`${API_BASE}/projects/${encodeURIComponent(DEMO_PROJECT_ID)}/sources`);
  return readJsonResponse(response);
}

export async function askQuestion({ query, history, debug, document, commit, repository }) {
  const response = await fetch(`${API_BASE}/query`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      project_id: DEMO_PROJECT_ID,
      question: query,
      ...(document ? { document } : {}),
      ...(commit ? { commit, repository } : {}),
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
