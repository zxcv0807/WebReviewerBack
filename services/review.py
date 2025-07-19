from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field
from typing import List, Optional
from datetime import datetime
from supabase import create_client, Client
import os

SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_ANON_KEY = os.getenv("SUPABASE_ANON_KEY")
if not SUPABASE_URL or not SUPABASE_ANON_KEY:
    raise RuntimeError("SUPABASE_URL and SUPABASE_ANON_KEY must be set in .env")
supabase: Client = create_client(SUPABASE_URL, SUPABASE_ANON_KEY)

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
    average_rating: Optional[float] = None
    comments: List[CommentResponse]

# API Endpoints
@router.post("/reviews", response_model=ReviewResponse)
def create_review(review: ReviewCreate):
    # 중복 체크: url이 이미 존재하면 에러 반환
    exists = supabase.table("review").select("id").eq("url", review.url).execute().data
    if exists:
        raise HTTPException(status_code=400, detail="이미 리뷰가 등록된 사이트입니다.")
    now = datetime.utcnow().isoformat()
    review_result = supabase.table("review").insert({
        "site_name": review.site_name,
        "url": review.url,
        "summary": review.summary,
        "rating": review.rating,
        "pros": review.pros,
        "cons": review.cons,
        "created_at": now
    }).execute()
    review_id = review_result.data[0]["id"]
    review_row = supabase.table("review").select("*").eq("id", review_id).single().execute().data
    # rating 필드 제거해서 반환
    review_row.pop("rating", None)
    return ReviewResponse(**review_row)

@router.get("/reviews", response_model=List[ReviewWithCommentsResponse])
def get_reviews():
    reviews = supabase.table("review").select("*").order("created_at", desc=True).execute().data
    comments = supabase.table("review_comment").select("*").order("created_at").execute().data
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
    return list(reviews_dict.values())

@router.get("/reviews/{review_id}", response_model=ReviewWithCommentsResponse)
def get_review(review_id: int):
    review_row = supabase.table("review").select("*").eq("id", review_id).single().execute().data
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
def update_review(review_id: int, review_update: ReviewUpdate):
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
def delete_review(review_id: int):
    # 댓글 먼저 삭제
    supabase.table("review_comment").delete().eq("review_id", review_id).execute()
    # 리뷰 삭제
    supabase.table("review").delete().eq("id", review_id).execute()
    return {"msg": "Review deleted successfully"} 