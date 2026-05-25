from fastapi import APIRouter


router = APIRouter(tags=["health"])


@router.get("/health", summary="API status")
def get_health() -> dict[str, str]:
    return {"status": "ok"}