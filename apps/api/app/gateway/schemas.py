from pydantic import BaseModel


class SlotPoolResponse(BaseModel):
    available: int
    total: int
    threshold: int
    healthy: bool
