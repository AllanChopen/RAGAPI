from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.schemas.item_schema import ItemCreate, ItemResponse
from app.services.item_service import ItemService
from app.views.item_view import to_item_response, to_item_response_list


router = APIRouter(prefix="/items", tags=["items"])


@router.get("/", response_model=list[ItemResponse], summary="List all items")
def list_items(db: Session = Depends(get_db)) -> list[ItemResponse]:
    try:
        items = ItemService(db).list_items()
        return to_item_response_list(items)
    except SQLAlchemyError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Database unavailable. Check MySQL connection settings.",
        ) from exc


@router.post(
    "/",
    response_model=ItemResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create an item",
)
def create_item(payload: ItemCreate, db: Session = Depends(get_db)) -> ItemResponse:
    try:
        item = ItemService(db).create_item(payload)
        return to_item_response(item)
    except SQLAlchemyError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Database unavailable. Check MySQL connection settings.",
        ) from exc