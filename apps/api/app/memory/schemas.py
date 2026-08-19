from uuid import UUID

from pydantic import BaseModel


class MemoryResultSchema(BaseModel):
    text: str
    dataset_name: str
    source: str
    score: float | None = None


class MemorySearchRequest(BaseModel):
    query: str
    employee_id: UUID


class MemorySearchResponse(BaseModel):
    results: list[MemoryResultSchema]
    query: str


class MemoryIngestRequest(BaseModel):
    content: str
    employee_id: UUID


class MemoryIngestResponse(BaseModel):
    status: str
