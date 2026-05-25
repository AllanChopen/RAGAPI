from fastapi import APIRouter, HTTPException, status
import httpx

from app.schemas.hf_schema import HFTestRequest, HFTestResponse
from app.services.hf_service import HFService


router = APIRouter(prefix="/hf", tags=["huggingface"])


@router.post("/test", response_model=HFTestResponse, summary="Test Hugging Face Inference API")
def test_hf_inference(payload: HFTestRequest) -> HFTestResponse:
    try:
        output, raw = HFService.infer(
            prompt=payload.prompt,
            max_new_tokens=payload.max_new_tokens,
            temperature=payload.temperature,
        )
        return HFTestResponse(output=output, raw=raw)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(exc)) from exc
    except httpx.HTTPStatusError as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Hugging Face API error: {exc.response.text}",
        ) from exc
    except httpx.HTTPError as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Unable to connect to Hugging Face API: {str(exc)}",
        ) from exc
