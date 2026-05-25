from app.models.item import Item
from app.schemas.item_schema import ItemResponse


def to_item_response(item: Item) -> ItemResponse:
    return ItemResponse.model_validate(item)


def to_item_response_list(items: list[Item]) -> list[ItemResponse]:
    return [to_item_response(item) for item in items]