from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from app.database import get_db
from app.models.models import PlantCustomer

router = APIRouter(prefix="/customers", tags=["Customers"])

@router.get("/{plant_id}")
def get_customers(plant_id: int, db: Session = Depends(get_db)):
    customers = db.query(PlantCustomer).filter(
        PlantCustomer.plant_id == plant_id
    ).all()
    return {"customers": [c.customer_name for c in customers]}