from sqlalchemy.orm import Session

import re
from app.core.settings import settings
from app.schemas.rag_schema import RAGAskRequest, RAGAskResponse, RAGCitation
from app.schemas.vector_schema import VectorSearchRequest
from app.services.hf_service import HFService
from app.services.vector_service import VectorService
from app.services.embedding_service import EmbeddingService
from app.models.context_chunk import ContextChunk


class RAGService:
    @staticmethod
    def _build_prompt_and_citations(db: Session, payload: RAGAskRequest) -> tuple[str, list[RAGCitation]]:
        # First perform vector search
        retrieval = VectorService.semantic_search(
            db,
            VectorSearchRequest(query=payload.query, top_k=payload.top_k, source=payload.source),
        )

        # If uploaded sources are involved, also do a simple text-based search on uploaded chunks
        # and merge those results first to prioritize uploaded content for short/keyword queries.
        extra_matches = []
        try:
            uploaded_flag = False
            if payload.source is None:
                uploaded_flag = True
            elif isinstance(payload.source, list):
                uploaded_flag = any(isinstance(s, str) and (s == "uploaded" or s.startswith("uploaded:")) for s in payload.source)
            elif isinstance(payload.source, str) and ("uploaded:" in payload.source or payload.source == "uploaded"):
                uploaded_flag = True

            if uploaded_flag:
                # simple substring match (case-insensitive) on uploaded chunks
                pattern = f"%{payload.query}%"
                rows = db.query(ContextChunk).filter(ContextChunk.source.like('uploaded:%')).filter(
                    ContextChunk.content.ilike(pattern)
                ).limit(payload.top_k).all()

                # If no direct substring matches, try keyword-based fallback (e.g., tabla/campos)
                if not rows:
                    qlow = (payload.query or "").lower()
                    keywords = ["tabla", "tablas", "campo", "campos", "columna", "columnas"]
                    for kw in keywords:
                        if kw in qlow:
                            kpat = f"%{kw}%"
                            rows = db.query(ContextChunk).filter(ContextChunk.source.like('uploaded:%')).filter(
                                ContextChunk.content.ilike(kpat)
                            ).limit(payload.top_k).all()
                            if rows:
                                break

                # Additional fallback for architecture/diagram queries (drawio)
                if not rows:
                    qlow = (payload.query or "").lower()
                    arch_terms = ["diagrama", "arquitect", "drawio", "diagram", "arquitectura"]
                    if any(t in qlow for t in arch_terms):
                        for at in ["arquitect", "diagrama", "drawio", "arquitectura", "diagram"]:
                            kpat = f"%{at}%"
                            rows = db.query(ContextChunk).filter(ContextChunk.source.like('uploaded:%')).filter(
                                ContextChunk.content.ilike(kpat)
                            ).limit(payload.top_k).all()
                            if rows:
                                break

                # compute similarity using embeddings to rank them
                q_emb = EmbeddingService.embed_text(payload.query)
                for row in rows:
                    # row.embedding is a list-like
                    # compute cosine similarity
                    dot = sum(a * b for a, b in zip(q_emb, row.embedding))
                    norm_q = sum(a * a for a in q_emb) ** 0.5
                    norm_r = sum(a * a for a in row.embedding) ** 0.5
                    sim = 0.0
                    if norm_q and norm_r:
                        sim = max(0.0, min(1.0, dot / (norm_q * norm_r)))
                    extra_matches.append(
                        type('M', (), {
                            'id': row.id,
                            'source': row.source,
                            'content': row.content,
                            'metadata_json': row.metadata_json,
                            'similarity': sim,
                        })
                    )

            # If the query asks about a specific field (e.g., "campo telefono" or uses [telefono]),
            # perform a lexical search across non-uploaded sources (code) to find occurrences.
            field_name = None
            try:
                # look for [field] pattern
                m = re.search(r"\[([^\]]+)\]", (payload.query or ""))
                if m:
                    field_name = m.group(1).strip()
                else:
                    m2 = re.search(r"campo[s]?\s+([\w_]+)", (payload.query or "").lower())
                    if m2:
                        field_name = m2.group(1).strip()
            except Exception:
                field_name = None

            if field_name:
                try:
                    code_rows = db.query(ContextChunk).filter(~ContextChunk.source.like('uploaded:%')).filter(
                        ContextChunk.content.ilike(f"%{field_name}%")
                    ).limit(payload.top_k).all()
                    for row in code_rows:
                        extra_matches.append(
                            type('M', (), {
                                'id': row.id,
                                'source': row.source,
                                'content': row.content,
                                'metadata_json': row.metadata_json,
                                'similarity': 0.0,
                            })
                        )
                except Exception:
                    pass
        except Exception:
            extra_matches = []

        # merge extra_matches (uploaded text matches) with retrieval.matches, avoiding duplicates
        combined_matches = []
        seen_ids = set()
        for m in extra_matches:
            if m.id not in seen_ids:
                combined_matches.append(m)
                seen_ids.add(m.id)
        for m in retrieval.matches:
            if m.id not in seen_ids:
                combined_matches.append(m)
                seen_ids.add(m.id)

        # Apply hybrid re-ranking: combine embedding similarity with a simple lexical overlap score
        def lexical_score_for(match, query):
            try:
                qtokens = [t for t in re.findall(r"\w+", (query or "").lower()) if t]
                if not qtokens:
                    return 0.0
                content = (match.content or "").lower()
                ctokens = set(re.findall(r"\w+", content))
                if not ctokens:
                    return 0.0
                common = sum(1 for t in set(qtokens) if t in ctokens)
                return common / len(set(qtokens))
            except Exception:
                return 0.0

        alpha = 0.75  # weight for embedding similarity
        reranked = []
        for m in combined_matches:
            lex = lexical_score_for(m, payload.query)
            sim = getattr(m, 'similarity', 0.0) or 0.0
            combined_score = alpha * sim + (1.0 - alpha) * lex
            # create a plain dynamic object to avoid modifying Pydantic models
            obj = type('M', (), {
                'id': getattr(m, 'id'),
                'source': getattr(m, 'source'),
                'content': getattr(m, 'content'),
                'metadata_json': getattr(m, 'metadata_json', None),
                'similarity': sim,
                'combined_score': combined_score,
            })()
            reranked.append(obj)

        # sort by combined_score desc and set similarity to combined_score
        reranked.sort(key=lambda x: getattr(x, 'combined_score', 0.0), reverse=True)
        for obj in reranked:
            obj.similarity = getattr(obj, 'combined_score', 0.0)

        retrieval.matches = reranked

        context_blocks: list[str] = []
        citations: list[RAGCitation] = []

        for idx, match in enumerate(retrieval.matches, start=1):
            # Si el usuario seleccionó una fuente concreta, confiamos en esa fuente.
            # Esto evita "No hay evidencia..." cuando el repo/archivo sí fue cargado,
            # pero el embedding determinístico por hash devuelve baja similitud.
            min_sim = settings.rag_min_similarity
            content_low = (match.content or "").lower()

            allow_low = payload.source is not None

            # También permitimos diagramas aunque la similitud sea baja.
            if isinstance(match.source, str) and match.source.startswith("uploaded:"):
                if any(t in content_low for t in ["arquitect", "diagrama", "drawio", "diagram"]):
                    allow_low = True

            if match.similarity < min_sim and not allow_low:
                continue

            metadata = match.metadata_json or {}
            file_path = metadata.get("file_path")
            line_start = metadata.get("line_start")
            line_end = metadata.get("line_end")
            tab = metadata.get("tab")
            location = file_path or "unknown"
            if line_start and line_end:
                location = f"{location}:{line_start}-{line_end}"
            if tab:
                location = f"{location} [tab: {tab}]"

            context_blocks.append(
                "\n".join(
                    [
                        f"[Chunk {idx}]",
                        f"source: {match.source}",
                        f"location: {location}",
                        f"similarity: {match.similarity:.4f}",
                        f"content:\n{match.content}",
                    ]
                )
            )
            citations.append(
                RAGCitation(
                    chunk_id=match.id,
                    source=match.source,
                    similarity=match.similarity,
                    file_path=file_path,
                    line_start=int(line_start) if line_start is not None else None,
                    line_end=int(line_end) if line_end is not None else None,
                    tab=str(tab) if tab is not None else None,
                )
            )

        history_text = RAGService._format_history(payload.conversation_history)
        context_text = "\n\n".join(context_blocks) if context_blocks else "No relevant context found."

        prompt = (
            "You are a strict technical assistant for repository traceability. "
            "You MUST use only the provided retrieved context and citations. "
            "Do not use external or prior model knowledge. "
            "If evidence is insufficient, answer exactly: 'No hay evidencia suficiente en los documentos cargados.'\n\n"
            f"Conversation memory:\n{history_text}\n\n"
            f"User question:\n{payload.query}\n\n"
            f"Retrieved context:\n{context_text}\n\n"
            "Return a concise answer in Spanish and include a short 'Fuentes' section with file and line/tab references."
        )

        return prompt, citations

    @staticmethod
    def ask(db: Session, payload: RAGAskRequest) -> RAGAskResponse:
        prompt, citations = RAGService._build_prompt_and_citations(db, payload)

        # If debug requested, return raw retrieval candidates in debug_matches
        debug_matches = None
        if payload.debug:
            # prepare debug info from the retrieval step (citations candidates)
            debug_matches = [
                {
                    "chunk_id": c.chunk_id,
                    "source": c.source,
                    "similarity": c.similarity,
                    "file_path": c.file_path,
                    "line_start": c.line_start,
                    "line_end": c.line_end,
                    "tab": c.tab,
                }
                for c in citations
            ]

        if not citations:
            answer = "No hay evidencia suficiente en los documentos cargados."
            return RAGAskResponse(
                answer=answer,
                citations=[],
                context_chunks_used=0,
                retrieval_query=payload.query,
                model=settings.hf_model_name,
                debug_matches=debug_matches,
            )

        answer, _ = HFService.infer(
            prompt=prompt,
            max_new_tokens=payload.max_new_tokens,
            temperature=payload.temperature,
        )

        answer = RAGService._append_citations(answer, citations)

        return RAGAskResponse(
            answer=answer,
            citations=citations,
            context_chunks_used=len(citations),
            retrieval_query=payload.query,
            model=settings.hf_model_name,
            debug_matches=debug_matches,
        )

    @staticmethod
    def prepare_generation(db: Session, payload: RAGAskRequest) -> tuple[str, list[RAGCitation]]:
        return RAGService._build_prompt_and_citations(db, payload)

    @staticmethod
    def _format_history(history: list[dict[str, str]]) -> str:
        if not history:
            return "No previous turns"

        recent = history[-settings.rag_memory_turns :]
        lines: list[str] = []
        for idx, turn in enumerate(recent, start=1):
            user = turn.get("user", "")
            assistant = turn.get("assistant", "")
            lines.append(f"Turn {idx} user: {user}")
            lines.append(f"Turn {idx} assistant: {assistant}")
        return "\n".join(lines)

    @staticmethod
    def _append_citations(answer: str, citations: list[RAGCitation]) -> str:
        lines: list[str] = [answer.strip(), "", "Fuentes:"]
        for citation in citations:
            location = citation.file_path or "unknown"
            if citation.line_start and citation.line_end:
                location = f"{location}:{citation.line_start}-{citation.line_end}"
            if citation.tab:
                location = f"{location} [tab: {citation.tab}]"
            lines.append(f"- {location}")
        return "\n".join(lines).strip()
