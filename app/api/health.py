from fastapi import APIRouter

from app.db.schemas import HealthRead

router = APIRouter()


@router.get("/health", response_model=HealthRead)
def health() -> HealthRead:
    return HealthRead(status="ok")
