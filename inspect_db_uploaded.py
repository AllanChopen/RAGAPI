from app.core.database import SessionLocal
from app.models.context_chunk import ContextChunk

db = SessionLocal()
rows = db.query(ContextChunk).filter(ContextChunk.source.like('uploaded:%')).order_by(ContextChunk.id.desc()).limit(10).all()
print('found', len(rows))
for r in rows:
    print('--- id', r.id, 'source', r.source)
    print(r.content[:400])
    print()
db.close()
