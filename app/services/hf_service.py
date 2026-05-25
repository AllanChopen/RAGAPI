import json

import httpx

from app.core.settings import settings


class HFService:
    @staticmethod
    def infer(prompt: str, max_new_tokens: int, temperature: float) -> tuple[str, list[dict] | dict]:
        if not settings.hf_api_token:
            raise ValueError("HF_API_TOKEN is not configured")

        headers = {
            "Authorization": f"Bearer {settings.hf_api_token}",
            "Content-Type": "application/json",
        }

        payload = {
            "model": settings.hf_model_name,
            "messages": [{"role": "user", "content": prompt}],
            "max_tokens": max_new_tokens,
            "temperature": temperature,
        }

        with httpx.Client(timeout=60.0) as client:
            response = client.post(settings.hf_model_url, headers=headers, json=payload)
            response.raise_for_status()
            data = response.json()

        text = ""
        if isinstance(data, dict):
            choices = data.get("choices")
            if isinstance(choices, list) and choices:
                first_choice = choices[0]
                if isinstance(first_choice, dict):
                    message = first_choice.get("message")
                    if isinstance(message, dict):
                        text = str(message.get("content", ""))

        return text, data

    @staticmethod
    def infer_stream(prompt: str, max_new_tokens: int, temperature: float):
        if not settings.hf_api_token:
            raise ValueError("HF_API_TOKEN is not configured")

        headers = {
            "Authorization": f"Bearer {settings.hf_api_token}",
            "Content-Type": "application/json",
            "Accept": "text/event-stream",
        }

        payload = {
            "model": settings.hf_model_name,
            "messages": [{"role": "user", "content": prompt}],
            "max_tokens": max_new_tokens,
            "temperature": temperature,
            "stream": True,
        }

        with httpx.Client(timeout=120.0) as client:
            with client.stream("POST", settings.hf_model_url, headers=headers, json=payload) as response:
                response.raise_for_status()
                for line in response.iter_lines():
                    if not line:
                        continue
                    if not line.startswith("data: "):
                        continue

                    data_line = line.removeprefix("data: ").strip()
                    if data_line == "[DONE]":
                        break

                    try:
                        event = json.loads(data_line)
                    except json.JSONDecodeError:
                        continue

                    choices = event.get("choices")
                    if not isinstance(choices, list) or not choices:
                        continue

                    first_choice = choices[0]
                    if not isinstance(first_choice, dict):
                        continue

                    delta = first_choice.get("delta")
                    if not isinstance(delta, dict):
                        continue

                    content = delta.get("content")
                    if isinstance(content, str) and content:
                        yield content
