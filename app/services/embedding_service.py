import math
from collections.abc import Sequence

import httpx
from huggingface_hub import InferenceClient

from app.core.settings import settings


class EmbeddingService:
    _hf_client: InferenceClient | None = None

    @classmethod
    def embed_text(cls, text: str) -> list[float]:
        embeddings = cls.embed_texts([text])
        return embeddings[0]

    @classmethod
    def embed_texts(cls, texts: Sequence[str]) -> list[list[float]]:
        clean_texts = [str(text or "").strip() for text in texts]
        if not clean_texts or any(not text for text in clean_texts):
            raise ValueError("El texto para generar embeddings no puede estar vacío")

        provider = settings.embedding_provider.strip().lower()
        try:
            if provider == "huggingface":
                vectors = cls._embed_huggingface(clean_texts)
            elif provider == "openai":
                vectors = cls._embed_openai(clean_texts)
            else:
                raise ValueError("EMBEDDING_PROVIDER no soportado. Use huggingface u openai")
        except ValueError:
            raise
        except Exception as exc:
            raise RuntimeError(
                f"Falló el proveedor de embeddings '{provider}': {exc}"
            ) from exc

        return [cls._fit_storage_dimensions(vector) for vector in vectors]

    @staticmethod
    def is_configured() -> bool:
        provider = settings.embedding_provider.strip().lower()
        if provider == "huggingface":
            return bool(settings.hf_api_token and settings.embedding_model_name)
        if provider == "openai":
            return bool(settings.openai_api_key and settings.openai_embedding_model_name)
        return False

    @classmethod
    def _embed_huggingface(cls, texts: list[str]) -> list[list[float]]:
        if not settings.hf_api_token:
            raise ValueError("HF_API_TOKEN es obligatorio para generar embeddings con Hugging Face")

        if cls._hf_client is None:
            cls._hf_client = InferenceClient(
                provider="hf-inference",
                api_key=settings.hf_api_token,
            )

        result = cls._hf_client.feature_extraction(
            texts,
            model=settings.embedding_model_name,
            normalize=True,
        )
        raw = result.tolist() if hasattr(result, "tolist") else result
        vectors = cls._normalize_embedding_response(raw, len(texts))
        return [cls._normalize(vector) for vector in vectors]

    @staticmethod
    def _embed_openai(texts: list[str]) -> list[list[float]]:
        if not settings.openai_api_key:
            raise ValueError("OPENAI_API_KEY es obligatorio para generar embeddings con OpenAI")

        payload = {
            "model": settings.openai_embedding_model_name,
            "input": texts,
            "dimensions": settings.embedding_dimensions,
            "encoding_format": "float",
        }
        headers = {
            "Authorization": f"Bearer {settings.openai_api_key}",
            "Content-Type": "application/json",
        }
        url = f"{settings.openai_base_url.rstrip('/')}/embeddings"

        with httpx.Client(timeout=settings.llm_timeout_seconds) as client:
            response = client.post(url, headers=headers, json=payload)
            response.raise_for_status()
            data = response.json()

        rows = data.get("data") if isinstance(data, dict) else None
        if not isinstance(rows, list) or len(rows) != len(texts):
            raise RuntimeError("OpenAI devolvió una respuesta de embeddings inválida")

        rows = sorted(rows, key=lambda item: int(item.get("index", 0)))
        return [EmbeddingService._normalize(list(item["embedding"])) for item in rows]

    @staticmethod
    def _normalize_embedding_response(raw, expected_count: int) -> list[list[float]]:
        if expected_count == 1 and isinstance(raw, list):
            if raw and all(isinstance(value, (int, float)) for value in raw):
                return [[float(value) for value in raw]]
            if len(raw) == 1 and isinstance(raw[0], list):
                first = raw[0]
                if first and all(isinstance(value, (int, float)) for value in first):
                    return [[float(value) for value in first]]

        if not isinstance(raw, list) or len(raw) != expected_count:
            raise RuntimeError("Hugging Face devolvió una estructura de embeddings inesperada")

        vectors: list[list[float]] = []
        for item in raw:
            if not isinstance(item, list):
                raise RuntimeError("Hugging Face devolvió un elemento de embedding inesperado")

            if item and all(isinstance(value, (int, float)) for value in item):
                vectors.append([float(value) for value in item])
                continue

            if item and isinstance(item[0], list):
                token_vectors = [
                    token
                    for token in item
                    if isinstance(token, list) and token
                ]
                if not token_vectors:
                    raise RuntimeError("Hugging Face no devolvió valores de embedding")
                dimensions = len(token_vectors[0])
                pooled = [
                    sum(float(token[index]) for token in token_vectors) / len(token_vectors)
                    for index in range(dimensions)
                ]
                vectors.append(pooled)
                continue

            raise RuntimeError("Hugging Face devolvió una estructura de embeddings inesperada")

        return vectors

    @staticmethod
    def _fit_storage_dimensions(vector: list[float]) -> list[float]:
        dimensions = settings.embedding_dimensions
        if len(vector) > dimensions:
            raise ValueError(
                f"El modelo de embeddings devolvió {len(vector)} dimensiones, pero el almacenamiento soporta {dimensions}. "
                "Aumente EMBEDDING_DIMENSIONS o utilice un modelo de embeddings compatible."
            )
        if len(vector) < dimensions:
            vector = vector + [0.0] * (dimensions - len(vector))
        return vector

    @staticmethod
    def _normalize(vector: list[float]) -> list[float]:
        norm = math.sqrt(sum(float(value) ** 2 for value in vector))
        if norm == 0:
            return [float(value) for value in vector]
        return [float(value) / norm for value in vector]
