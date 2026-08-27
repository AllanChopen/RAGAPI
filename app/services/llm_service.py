from dataclasses import dataclass

import httpx

from app.core.settings import settings


@dataclass(frozen=True)
class LLMResult:
    text: str
    provider: str
    model: str


class LLMService:
    @staticmethod
    def generate(
        system_prompt: str,
        user_prompt: str,
        max_tokens: int,
    ) -> LLMResult:
        provider = settings.llm_provider.strip().lower()

        if provider == "huggingface":
            return LLMService._openai_chat_completion(
                base_url=settings.hf_model_url.rsplit("/chat/completions", 1)[0],
                api_key=settings.hf_api_token,
                model=settings.hf_model_name,
                provider="huggingface",
                system_prompt=system_prompt,
                user_prompt=user_prompt,
                max_tokens=max_tokens,
            )

        if provider == "openai":
            return LLMService._openai_response(
                system_prompt=system_prompt,
                user_prompt=user_prompt,
                max_tokens=max_tokens,
            )

        if provider == "anthropic":
            return LLMService._anthropic_message(
                system_prompt=system_prompt,
                user_prompt=user_prompt,
                max_tokens=max_tokens,
            )

        if provider == "openai_compatible":
            if not settings.openai_compatible_base_url or not settings.openai_compatible_model_name:
                raise ValueError(
                    "OPENAI_COMPATIBLE_BASE_URL y OPENAI_COMPATIBLE_MODEL_NAME son obligatorios"
                )
            return LLMService._openai_chat_completion(
                base_url=settings.openai_compatible_base_url,
                api_key=settings.openai_compatible_api_key,
                model=settings.openai_compatible_model_name,
                provider="openai_compatible",
                system_prompt=system_prompt,
                user_prompt=user_prompt,
                max_tokens=max_tokens,
            )

        raise ValueError(
            "LLM_PROVIDER no soportado. Use huggingface, openai, anthropic u openai_compatible"
        )

    @staticmethod
    def is_configured() -> bool:
        provider = settings.llm_provider.strip().lower()
        if provider == "huggingface":
            return bool(settings.hf_api_token and settings.hf_model_name)
        if provider == "openai":
            return bool(settings.openai_api_key and settings.openai_model_name)
        if provider == "anthropic":
            return bool(settings.anthropic_api_key and settings.anthropic_model_name)
        if provider == "openai_compatible":
            return bool(
                settings.openai_compatible_base_url
                and settings.openai_compatible_model_name
            )
        return False

    @staticmethod
    def _openai_response(
        system_prompt: str,
        user_prompt: str,
        max_tokens: int,
    ) -> LLMResult:
        if not settings.openai_api_key:
            raise ValueError("OPENAI_API_KEY no está configurado")

        headers = {
            "Authorization": f"Bearer {settings.openai_api_key}",
            "Content-Type": "application/json",
        }
        payload = {
            "model": settings.openai_model_name,
            "instructions": system_prompt,
            "input": user_prompt,
            "max_output_tokens": max_tokens,
        }
        url = f"{settings.openai_base_url.rstrip('/')}/responses"

        with httpx.Client(timeout=settings.llm_timeout_seconds) as client:
            response = client.post(url, headers=headers, json=payload)
            response.raise_for_status()
            data = response.json()

        text = LLMService._extract_openai_response_text(data)
        if not text:
            raise RuntimeError("OpenAI devolvió una respuesta vacía")

        return LLMResult(
            text=text,
            provider="openai",
            model=settings.openai_model_name,
        )

    @staticmethod
    def _extract_openai_response_text(data: dict) -> str:
        output_text = data.get("output_text")
        if isinstance(output_text, str) and output_text.strip():
            return output_text.strip()

        parts: list[str] = []
        for item in data.get("output", []):
            if not isinstance(item, dict) or item.get("type") != "message":
                continue
            for content in item.get("content", []):
                if not isinstance(content, dict):
                    continue
                if content.get("type") in {"output_text", "text"}:
                    text = content.get("text")
                    if isinstance(text, str) and text.strip():
                        parts.append(text.strip())
        return "\n".join(parts).strip()

    @staticmethod
    def _openai_chat_completion(
        base_url: str,
        api_key: str | None,
        model: str,
        provider: str,
        system_prompt: str,
        user_prompt: str,
        max_tokens: int,
    ) -> LLMResult:
        if not api_key and provider != "openai_compatible":
            raise ValueError(f"La API key no está configurada para el proveedor '{provider}'")

        headers = {"Content-Type": "application/json"}
        if api_key:
            headers["Authorization"] = f"Bearer {api_key}"

        payload = {
            "model": model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            "max_tokens": max_tokens,
        }

        url = f"{base_url.rstrip('/')}/chat/completions"
        with httpx.Client(timeout=settings.llm_timeout_seconds) as client:
            response = client.post(url, headers=headers, json=payload)
            response.raise_for_status()
            data = response.json()

        choices = data.get("choices") if isinstance(data, dict) else None
        if not isinstance(choices, list) or not choices:
            raise RuntimeError(f"El proveedor '{provider}' no devolvió opciones de respuesta")

        message = choices[0].get("message", {})
        text = message.get("content") if isinstance(message, dict) else None
        if not isinstance(text, str) or not text.strip():
            raise RuntimeError(f"El proveedor '{provider}' devolvió una respuesta vacía")

        return LLMResult(text=text.strip(), provider=provider, model=model)

    @staticmethod
    def _anthropic_message(
        system_prompt: str,
        user_prompt: str,
        max_tokens: int,
    ) -> LLMResult:
        if not settings.anthropic_api_key:
            raise ValueError("ANTHROPIC_API_KEY no está configurado")

        headers = {
            "x-api-key": settings.anthropic_api_key,
            "anthropic-version": settings.anthropic_version,
            "content-type": "application/json",
        }
        payload = {
            "model": settings.anthropic_model_name,
            "system": system_prompt,
            "messages": [{"role": "user", "content": user_prompt}],
            "max_tokens": max_tokens,
        }

        url = f"{settings.anthropic_base_url.rstrip('/')}/messages"
        with httpx.Client(timeout=settings.llm_timeout_seconds) as client:
            response = client.post(url, headers=headers, json=payload)
            response.raise_for_status()
            data = response.json()

        content = data.get("content") if isinstance(data, dict) else None
        if not isinstance(content, list):
            raise RuntimeError("Anthropic devolvió una respuesta inválida")

        parts = [
            block.get("text", "")
            for block in content
            if isinstance(block, dict) and block.get("type") == "text"
        ]
        text = "\n".join(part for part in parts if part).strip()
        if not text:
            raise RuntimeError("Anthropic devolvió una respuesta vacía")

        return LLMResult(
            text=text,
            provider="anthropic",
            model=settings.anthropic_model_name,
        )
