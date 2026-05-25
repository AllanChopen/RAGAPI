import hashlib
import math

from app.core.settings import settings


class EmbeddingService:
    @staticmethod
    def embed_text(text: str) -> list[float]:
        dims = settings.embedding_dimensions
        values: list[float] = []
        counter = 0

        while len(values) < dims:
            digest = hashlib.blake2b(f"{text}|{counter}".encode("utf-8"), digest_size=64).digest()
            for idx in range(0, len(digest), 4):
                raw = int.from_bytes(digest[idx : idx + 4], byteorder="big", signed=False)
                value = (raw / 4294967295.0) * 2.0 - 1.0
                values.append(value)
                if len(values) == dims:
                    break
            counter += 1

        norm = math.sqrt(sum(v * v for v in values))
        if norm == 0.0:
            return values

        return [v / norm for v in values]
