from app.core.database import SessionLocal
from app.models.context_chunk import ContextChunk
from app.services.embedding_service import EmbeddingService
import math

query = 'que campos hay en el diccionario?'
q_emb = EmbeddingService.embed_text(query)

def cosine(a,b):
    dot = sum(x*y for x,y in zip(a,b))
    na = math.sqrt(sum(x*x for x in a))
    nb = math.sqrt(sum(x*x for x in b))
    if na==0 or nb==0: return 0.0
    return dot/(na*nb)

db = SessionLocal()
rows = db.query(ContextChunk).filter(ContextChunk.source.like('uploaded:%')).all()
print('found', len(rows))
for r in rows:
    emb = r.embedding
    sim = cosine(q_emb, emb)
    print(r.id, sim)
    print(r.content[:200])
    print()

db.close()
