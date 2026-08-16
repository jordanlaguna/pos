from sqlalchemy.orm import Session
from app.models.model_categories import Category
from app.schemas.schemas_categories import CategoryRegister, CategoryResponse, AddCategories

def create_category(db: Session, category: CategoryRegister):
    # Create a new category instance
    db_category = Category(name=category.name)
    db.add(db_category)
    db.commit()
    db.refresh(db_category)

    return AddCategories(id=db_category.id, name=db_category.name)

def get_all_categories(db: Session):
    # Retrieve all categories from the database
    return db.query(Category).all()
