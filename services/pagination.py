from pydantic import BaseModel, Field
from typing import List, TypeVar, Generic, Any
from math import ceil

T = TypeVar('T')

class PaginationParams(BaseModel):
    page: int = Field(default=1, ge=1, description="페이지 번호 (1부터 시작)")
    limit: int = Field(default=10, ge=1, le=10, description="페이지당 항목 수 (최대 10)")

class PaginationInfo(BaseModel):
    current_page: int
    total_pages: int
    total_count: int
    has_next: bool
    has_previous: bool

class PaginatedResponse(BaseModel, Generic[T]):
    data: List[T]
    pagination: PaginationInfo

def create_pagination_info(page: int, limit: int, total_count: int) -> PaginationInfo:
    total_pages = ceil(total_count / limit) if total_count > 0 else 1
    
    return PaginationInfo(
        current_page=page,
        total_pages=total_pages,
        total_count=total_count,
        has_next=page < total_pages,
        has_previous=page > 1
    )

def get_offset(page: int, limit: int) -> int:
    return (page - 1) * limit