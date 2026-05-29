export const dom = {
  ingestForm: document.getElementById("ingestForm"),
  repoUrl: document.getElementById("repoUrl"),
  filesInput: document.getElementById("filesInput"),
  ingestButton: document.getElementById("ingestButton"),
  resetButton: document.getElementById("resetButton"),
  ingestStatus: document.getElementById("ingestStatus"),
  sourceList: document.getElementById("sourceList"),
  sourceSummary: document.getElementById("sourceSummary"),
  chatHint: document.getElementById("chatHint"),
  chatMessages: document.getElementById("chatMessages"),
  chatForm: document.getElementById("chatForm"),
  messageInput: document.getElementById("messageInput"),
  sendButton: document.getElementById("sendButton"),
  debugToggle: document.getElementById("debugToggle"),
  debugPanel: document.getElementById("debugPanel"),
  debugContent: document.getElementById("debugContent"),
  year: document.getElementById("year"),
};

export function escapeHtml(value) {
  return String(value || "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#039;");
}

function renderInlineMarkdown(value) {
  return escapeHtml(value)
    .replace(/`([^`]+)`/g, "<code>$1</code>")
    .replace(/\*\*([^*]+)\*\*/g, "<strong>$1</strong>")
    .replace(/\*([^*]+)\*/g, "<em>$1</em>");
}

function renderMarkdown(value) {
  const text = String(value || "Sin respuesta.").replace(/\r\n/g, "\n");
  const lines = text.split("\n");

  let html = "";
  let currentList = null;
  let inCodeBlock = false;
  let codeBuffer = [];

  function closeList() {
    if (currentList) {
      html += `</${currentList}>`;
      currentList = null;
    }
  }

  function openList(type) {
    if (currentList === type) {
      return;
    }

    closeList();
    currentList = type;
    html += `<${type}>`;
  }

  function closeCodeBlock() {
    html += `<pre><code>${escapeHtml(codeBuffer.join("\n"))}</code></pre>`;
    codeBuffer = [];
    inCodeBlock = false;
  }

  for (const rawLine of lines) {
    const line = rawLine.trim();

    if (line.startsWith("```")) {
      if (inCodeBlock) {
        closeCodeBlock();
      } else {
        closeList();
        inCodeBlock = true;
        codeBuffer = [];
      }

      continue;
    }

    if (inCodeBlock) {
      codeBuffer.push(rawLine);
      continue;
    }

    if (!line) {
      closeList();
      continue;
    }

    const headingMatch = line.match(/^(#{1,4})\s+(.+)$/);
    if (headingMatch) {
      closeList();
      const level = headingMatch[1].length;
      html += `<h${level}>${renderInlineMarkdown(headingMatch[2])}</h${level}>`;
      continue;
    }

    const orderedMatch = line.match(/^\d+\.\s+(.+)$/);
    if (orderedMatch) {
      openList("ol");
      html += `<li>${renderInlineMarkdown(orderedMatch[1])}</li>`;
      continue;
    }

    const unorderedMatch = line.match(/^[-*]\s+(.+)$/);
    if (unorderedMatch) {
      openList("ul");
      html += `<li>${renderInlineMarkdown(unorderedMatch[1])}</li>`;
      continue;
    }

    closeList();
    html += `<p>${renderInlineMarkdown(line)}</p>`;
  }

  closeList();

  if (inCodeBlock) {
    closeCodeBlock();
  }

  return `<div class="markdown-body">${html}</div>`;
}

export function setLoading(isLoading) {
  dom.ingestButton.disabled = isLoading;
  dom.sendButton.disabled = isLoading || dom.messageInput.disabled;
  dom.resetButton.disabled = isLoading;
}

export function setNotice(type, message) {
  const className = {
    muted: "notice notice-muted",
    success: "notice notice-success",
    error: "notice notice-error",
  }[type] || "notice notice-muted";

  dom.ingestStatus.className = className;
  dom.ingestStatus.textContent = message;
}

export function renderSourceSummary(sources) {
  const hasSources = sources.length > 0;
  const dotClass = hasSources ? "status-dot status-dot--ready" : "status-dot status-dot--empty";
  const title = hasSources ? `${sources.length} fuente(s) cargada(s)` : "Sin fuentes cargadas";
  const subtitle = hasSources
    ? "Ya puedes hacer preguntas sobre el conocimiento ingresado."
    : "La IA todavía no tiene contexto del proyecto.";

  dom.sourceSummary.innerHTML = `
    <span class="${dotClass}"></span>
    <div>
      <strong>${escapeHtml(title)}</strong>
      <small>${escapeHtml(subtitle)}</small>
    </div>
  `;
}

export function renderSourceList(sources) {
  if (!sources.length) {
    dom.sourceList.className = "source-list-empty";
    dom.sourceList.textContent = "No has ingresado fuentes todavía.";
    return;
  }

  dom.sourceList.className = "";
  dom.sourceList.innerHTML = sources
    .map((source) => {
      const typeLabel = source.type === "repo" ? "Repositorio" : "Archivo(s)";
      const chunks = Number(source.chunks || 0);
      const chunksText = chunks > 0 ? `${chunks} chunk(s) indexado(s)` : "Indexado";

      return `
        <article class="source-card">
          <span class="pill">${escapeHtml(typeLabel)}</span>
          <strong>${escapeHtml(source.label)}</strong>
          <span class="source-meta">${escapeHtml(chunksText)}</span>
        </article>
      `;
    })
    .join("");
}

export function renderChatAvailability(isReady, isLoading) {
  dom.messageInput.disabled = !isReady || isLoading;
  dom.sendButton.disabled = !isReady || isLoading;
  dom.messageInput.placeholder = isReady
    ? "Pregunta sobre el repo, diccionario, diagrama o documentación..."
    : "Primero ingesta fuentes para habilitar preguntas...";
  dom.chatHint.textContent = isReady
    ? "La respuesta debe usar el contexto cargado y mostrar fuentes."
    : "Carga fuentes para desbloquear el chat.";
}

function formatAnswer(answer) {
  return renderMarkdown(answer || "Sin respuesta.");
}

function citationLocation(citation) {
  let location = citation.file_path || citation.source || "Fuente sin archivo";

  if (citation.line_start && citation.line_end) {
    location += `:${citation.line_start}-${citation.line_end}`;
  }

  if (citation.tab) {
    location += ` [tab: ${citation.tab}]`;
  }

  return location;
}

function renderCitations(citations) {
  if (!Array.isArray(citations) || citations.length === 0) {
    return "";
  }

  const items = citations
    .map((citation) => {
      const similarity = Number(citation.similarity || 0).toFixed(3);
      return `<li>${escapeHtml(citationLocation(citation))} · similitud ${escapeHtml(similarity)}</li>`;
    })
    .join("");

  return `
    <div class="citations">
      <strong>Fuentes recuperadas</strong>
      <ul>${items}</ul>
    </div>
  `;
}

function renderTurn(turn, index) {
  const citations = index === -1 ? [] : turn.citations;

  return `
    <div class="message message-user">
      <div class="bubble">
        <span class="message-label">Tú</span>
        ${escapeHtml(turn.user)}
      </div>
    </div>
    <div class="message message-assistant">
      <div class="bubble">
        <span class="message-label">IA</span>
        ${formatAnswer(turn.assistant)}
        ${renderCitations(citations)}
      </div>
    </div>
  `;
}

export function renderChat(history, pendingUser = null) {
  if (!history.length && !pendingUser) {
    dom.chatMessages.innerHTML = `
      <div class="empty-state">
        <div class="empty-icon">↥</div>
        <h3>Empieza cargando conocimiento</h3>
        <p>
          Cuando la ingesta termine verás las fuentes aquí y podrás preguntar, por ejemplo:
          “¿En qué archivos se usa el campo customer_id?”
        </p>
      </div>
    `;
    return;
  }

  const stableTurns = history.map((turn, index) => renderTurn(turn, index)).join("");
  const pendingTurn = pendingUser
    ? renderTurn({ user: pendingUser, assistant: "Pensando con las fuentes cargadas..." }, -1)
    : "";

  dom.chatMessages.innerHTML = `${stableTurns}${pendingTurn}`;
  dom.chatMessages.scrollTop = dom.chatMessages.scrollHeight;
}

export function renderDebug(response, enabled) {
  dom.debugPanel.classList.toggle("hidden", !enabled);

  if (!enabled) {
    return;
  }

  dom.debugContent.textContent = JSON.stringify(
    {
      answer: response?.answer,
      citations: response?.citations,
      context_chunks_used: response?.context_chunks_used,
      retrieval_query: response?.retrieval_query,
      debug_matches: response?.debug_matches,
    },
    null,
    2
  );
}

export function renderAll({ sources, history, isLoading, lastResponse, debugEnabled }) {
  const ready = sources.length > 0;
  renderSourceSummary(sources);
  renderSourceList(sources);
  renderChatAvailability(ready, isLoading);
  renderChat(history);
  renderDebug(lastResponse, debugEnabled);
}
