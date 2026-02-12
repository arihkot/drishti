"""Authentication router — simple session-based auth for CSIDC demo."""

import logging

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

logger = logging.getLogger(__name__)
router = APIRouter()

# Hardcoded demo credentials
DEMO_USERS = {
    "admin": {
        "password": "csidc2024",
        "name": "Admin Officer",
        "role": "admin",
        "department": "CSIDC Monitoring Cell",
        "designation": "Deputy General Manager",
        "employee_id": "CSIDC-DGM-001",
    },
    "inspector": {
        "password": "inspect123",
        "name": "Rajesh Kumar",
        "role": "inspector",
        "department": "Land Compliance Division",
        "designation": "Senior Inspector",
        "employee_id": "CSIDC-SI-042",
    },
}


class LoginRequest(BaseModel):
    username: str
    password: str


@router.post("/login")
async def login(req: LoginRequest):
    user = DEMO_USERS.get(req.username)
    if not user or user["password"] != req.password:
        raise HTTPException(status_code=401, detail="Invalid credentials")

    return {
        "success": True,
        "user": {
            "username": req.username,
            "name": user["name"],
            "role": user["role"],
            "department": user["department"],
            "designation": user["designation"],
            "employee_id": user["employee_id"],
        },
    }


@router.get("/me")
async def get_current_user():
    """Placeholder — in a real app this would validate a session/JWT."""
    return {"authenticated": False}
