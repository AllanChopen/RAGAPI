from fastapi import APIRouter
from fastapi.responses import FileResponse
from pathlib import Path

router = APIRouter()

FRONTEND_DIR = Path(__file__).resolve().parents[2].joinpath('frontend')

@router.get('/', include_in_schema=False)
def index():
    index_file = FRONTEND_DIR.joinpath('index.html')
    if not index_file.exists():
        from fastapi import HTTPException

        raise HTTPException(status_code=404, detail="Frontend index not found")
    return FileResponse(index_file)

@router.get('/frontend/{path:path}', include_in_schema=False)
def asset(path: str):
    file = FRONTEND_DIR.joinpath(path)
    if file.exists():
        return FileResponse(file)
    raise HTTPException(status_code=404, detail="Asset not found")
