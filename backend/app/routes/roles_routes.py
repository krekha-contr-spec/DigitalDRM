from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.models import RoleAccess
from app.schemas.schemas import RoleVerification

router = APIRouter(
    prefix="/roles",
    tags=["Roles"]
)

@router.get("/{plant_id}")
def get_plant_roles(plant_id: int, db: Session = Depends(get_db)):
    """
    Get all available roles for a specific plant
    Returns list of unique roles with person names and emails
    """
    try:
        role_records = (
            db.query(RoleAccess)
            .filter(RoleAccess.plant_id == plant_id)
            .all()
        )

        if not role_records:
            raise HTTPException(
                status_code=404,
                detail=f"No roles found for plant {plant_id}"
            )

        # Format roles uniquely
        roles = {}
        for record in role_records:
            if record.role not in roles:
                roles[record.role] = {
                    "role": record.role,
                    "person_name": record.person_name,
                    "email": record.email,
                    "plant_id": record.plant_id
                }

        return {
            "plant_id": plant_id,
            "roles": list(roles.values()),
            "total_roles": len(roles)
        }

    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=str(e)
        )


@router.post("/verify")
def verify_role_access(
    payload: RoleVerification,
    db: Session = Depends(get_db)
):
 
    try:
        # Query: Find matching person in that plant
        role_record = (
            db.query(RoleAccess)
            .filter(
                RoleAccess.plant_id == payload.plant_id,
                RoleAccess.email == payload.email
            )
            .first()
        )

        if not role_record:
            raise HTTPException(
                status_code=403,
                detail="❌ Name and email combination not found. You are not authorized to enter data."
            )

        # Check if name matches (fuzzy match - contains)
        if payload.person_name.lower() not in role_record.person_name.lower():
            # Also try exact match on email only, show error with available person
            raise HTTPException(
                status_code=403,
                detail=f"❌ Name mismatch. This email belongs to: {role_record.person_name}"
            )

        return {
            "success": True,
            "plant_id": payload.plant_id,
            "role": role_record.role,
            "person_name": role_record.person_name,
            "email": role_record.email,
            "message": f"✅ Verified as {role_record.role.upper()} for {role_record.person_name}"
        }

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Error verifying role: {str(e)}"
        )