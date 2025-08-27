from fastapi import APIRouter, HTTPException, Query, Depends
from .auth import get_current_user
from pydantic import BaseModel, Field
from typing import List, Optional
from datetime import datetime
from .db import supabase
from .pagination import PaginationParams, PaginatedResponse, create_pagination_info, get_offset
import os

router = APIRouter()

# Pydantic Models
class ReviewCreate(BaseModel):
    site_name: str = Field(..., description="사이트명")
    url: str = Field(..., description="사이트 링크")
    summary: str = Field(..., description="간단한 설명")
    rating: float = Field(..., ge=0, le=5, description="0~5점 사이 실수")
    pros: str = Field(..., description="장점")
    cons: str = Field(..., description="단점")

class ReviewUpdate(BaseModel):
    site_name: Optional[str] = None
    url: Optional[str] = None
    summary: Optional[str] = None
    rating: Optional[float] = Field(None, ge=0, le=5)
    pros: Optional[str] = None
    cons: Optional[str] = None

class ReviewResponse(BaseModel):
    id: int
    site_name: str
    url: str
    summary: str
    pros: str
    cons: str
    created_at: str
    view_count: int = 0

class CommentCreate(BaseModel):
    content: str = Field(..., description="댓글 내용")
    rating: Optional[float] = Field(None, ge=0, le=5, description="0~5점 사이 실수")

class CommentResponse(BaseModel):
    id: int
    review_id: int
    content: str
    rating: Optional[float]
    created_at: str

class ReviewWithCommentsResponse(BaseModel):
    id: int
    site_name: str
    url: str
    summary: str
    pros: str
    cons: str
    created_at: str
    view_count: int = 0
    average_rating: Optional[float] = None
    comments: List[CommentResponse]

# API Endpoints
@router.post("/reviews", response_model=ReviewResponse)
def create_review(review: ReviewCreate, current_user=Depends(get_current_user)):
    now = datetime.utcnow().isoformat()
    review_result = supabase.table("review").insert({
        "site_name": review.site_name,
        "url": review.url,
        "summary": review.summary,
        "rating": review.rating,
        "pros": review.pros,
        "cons": review.cons,
        "created_at": now,
        "view_count": 0,
        "user_id": current_user["id"]
    }).execute()
    review_id = review_result.data[0]["id"]
    review_row = supabase.table("review").select("*").eq("id", review_id).single().execute().data
    # rating 필드 제거해서 반환
    review_row.pop("rating", None)
    return ReviewResponse(**review_row)

@router.get("/reviews", response_model=PaginatedResponse[ReviewWithCommentsResponse])
def get_reviews(
    page: int = Query(default=1, ge=1, description="페이지 번호 (1부터 시작)"),
    limit: int = Query(default=10, ge=1, le=10, description="페이지당 항목 수 (최대 10)")
):
    # 총 개수 조회
    total_count = len(supabase.table("review").select("id").execute().data)
    
    # 페이지네이션을 적용한 리뷰 데이터 조회
    reviews = supabase.table("review").select("*").order("created_at", desc=True).range(get_offset(page, limit), get_offset(page, limit) + limit - 1).execute().data
    
    # 해당 리뷰들의 댓글만 조회
    review_ids = [r["id"] for r in reviews]
    if review_ids:
        comments = supabase.table("review_comment").select("*").in_("review_id", review_ids).order("created_at").execute().data
    else:
        comments = []
    
    reviews_dict = {r["id"]: ReviewWithCommentsResponse(**{k: v for k, v in r.items() if k != "rating"}, comments=[], average_rating=None) for r in reviews}
    
    # 댓글 추가 및 평균 별점 계산
    for c in comments:
        if c["review_id"] in reviews_dict:
            reviews_dict[c["review_id"]].comments.append(CommentResponse(**c))
    
    for review, rdata in zip(reviews_dict.values(), reviews):
        ratings = [c.rating for c in review.comments if c.rating is not None]
        if rdata["rating"] is not None:
            ratings.append(rdata["rating"])
        review.average_rating = sum(ratings) / len(ratings) if ratings else None
    
    pagination_info = create_pagination_info(page, limit, total_count)
    return PaginatedResponse(data=list(reviews_dict.values()), pagination=pagination_info)

@router.get("/reviews/{review_id}", response_model=ReviewWithCommentsResponse)
def get_review(review_id: int):
    # 리뷰 데이터 조회
    review_row = supabase.table("review").select("*").eq("id", review_id).single().execute().data
    if not review_row:
        raise HTTPException(status_code=404, detail="Review not found")
    
    # 조회수 증가
    current_view_count = review_row.get("view_count", 0)
    supabase.table("review").update({
        "view_count": current_view_count + 1
    }).eq("id", review_id).execute()
    
    # 업데이트된 view_count를 반영
    review_row["view_count"] = current_view_count + 1
    
    comments_data = supabase.table("review_comment").select("*").eq("review_id", review_id).order("created_at").execute().data
    comments = [CommentResponse(**c) for c in comments_data]
    ratings = [c["rating"] for c in comments_data if c.get("rating") is not None]
    if review_row["rating"] is not None:
        ratings.append(review_row["rating"])
    average_rating = sum(ratings) / len(ratings) if ratings else None
    # rating 필드 제거해서 반환
    review_row.pop("rating", None)
    return ReviewWithCommentsResponse(**review_row, comments=comments, average_rating=average_rating)

@router.post("/reviews/{review_id}/comments", response_model=CommentResponse)
def create_comment(review_id: int, comment: CommentCreate):
    # 리뷰 존재 확인
    review = supabase.table("review").select("id").eq("id", review_id).single().execute().data
    if not review:
        raise HTTPException(status_code=404, detail="Review not found")
    now = datetime.utcnow().isoformat()
    comment_result = supabase.table("review_comment").insert({
        "review_id": review_id,
        "content": comment.content,
        "rating": comment.rating,
        "created_at": now
    }).execute()
    comment_id = comment_result.data[0]["id"]
    comment_row = supabase.table("review_comment").select("*").eq("id", comment_id).single().execute().data
    return CommentResponse(**comment_row)

@router.put("/reviews/{review_id}", response_model=ReviewResponse)
def update_review(review_id: int, review_update: ReviewUpdate, current_user=Depends(get_current_user)):
    # 리뷰 존재 및 작성자 확인
    review_row = supabase.table("review").select("*").eq("id", review_id).single().execute().data
    if not review_row:
        raise HTTPException(status_code=404, detail="Review not found")
    
    if review_row["user_id"] != current_user["id"]:
        raise HTTPException(status_code=403, detail="You can only update your own reviews")
    
    update_fields = {}
    if review_update.site_name is not None:
        update_fields["site_name"] = review_update.site_name
    if review_update.url is not None:
        update_fields["url"] = review_update.url
    if review_update.summary is not None:
        update_fields["summary"] = review_update.summary
    if review_update.rating is not None:
        update_fields["rating"] = review_update.rating
    if review_update.pros is not None:
        update_fields["pros"] = review_update.pros
    if review_update.cons is not None:
        update_fields["cons"] = review_update.cons
    if update_fields:
        supabase.table("review").update(update_fields).eq("id", review_id).execute()
    review_row = supabase.table("review").select("*").eq("id", review_id).single().execute().data
    return ReviewResponse(**review_row)

@router.delete("/reviews/{review_id}")
def delete_review(review_id: int, current_user=Depends(get_current_user)):
    # 리뷰 존재 및 작성자 확인
    review_row = supabase.table("review").select("*").eq("id", review_id).single().execute().data
    if not review_row:
        raise HTTPException(status_code=404, detail="Review not found")
    
    if review_row["user_id"] != current_user["id"]:
        raise HTTPException(status_code=403, detail="You can only delete your own reviews")
    
    # 댓글 먼저 삭제
    supabase.table("review_comment").delete().eq("review_id", review_id).execute()
    # 리뷰 삭제
    supabase.table("review").delete().eq("id", review_id).execute()
    return {"msg": "Review deleted successfully"} 