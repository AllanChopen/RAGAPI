from sqlalchemy.orm import Session

from app.models.item import Item
from app.schemas.item_schema import ItemCreate


class ItemService:
    def __init__(self, db: Session) -> None:
        self.db = db

    def list_items(self) -> list[Item]:
        return self.db.query(Item).order_by(Item.id.asc()).all()

    def create_item(self, payload: ItemCreate) -> Item:
        item = Item(name=payload.name, description=payload.description)
        self.db.add(item)
        self.db.commit()
        self.db.refresh(item)
        return item