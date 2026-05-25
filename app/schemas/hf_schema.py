from pydantic import BaseModel


class HFTestRequest(BaseModel):
    prompt: str
    max_new_tokens: int = 128
    temperature: float = 0.2


class HFTestResponse(BaseModel):
    output: str
    raw: list[dict] | dict
