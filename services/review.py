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
class VoteCreate(BaseModel):
    vote_type: str = Field(..., pattern="^(like|dislike)$", description="투표 유형: 'like' 또는 'dislike'")

class VoteResponse(BaseModel):
    message: str
    like_count: int
    dislike_count: int
    user_vote_type: Optional[str] = None
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
    rating: float
    pros: str
    cons: str
    created_at: str
    updated_at: Optional[str] = None
    view_count: int = 0
    like_count: int = 0
    dislike_count: int = 0
    user_id: Optional[int]
    user_name: str = "알수없음"

class CommentCreate(BaseModel):
    content: str = Field(..., description="댓글 내용")

class CommentUpdate(BaseModel):
    content: Optional[str] = None

class CommentResponse(BaseModel):
    id: int
    review_id: int
    content: str
    created_at: str
    user_id: Optional[int]
    user_name: str = "알수없음"

class ReviewWithCommentsResponse(BaseModel):
    id: int
    site_name: str
    url: str
    summary: str
    rating: float
    pros: str
    cons: str
    created_at: str
    updated_at: Optional[str] = None
    view_count: int = 0
    like_count: int = 0
    dislike_count: int = 0
    user_id: Optional[int]
    user_name: str = "알수없음"
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
        "updated_at": now,
        "view_count": 0,
        "like_count": 0,
        "dislike_count": 0,
        "user_id": current_user["id"]
    }).execute()
    review_id = review_result.data[0]["id"]
    review_row = supabase.table("review").select("*").eq("id", review_id).single().execute().data
    
    user_name = "알수없음"
    if review_row.get("user_id"):
        user_row = supabase.table("user").select("username").eq("id", review_row["user_id"]).single().execute().data
        user_name = user_row["username"] if user_row else "알수없음"
    
    return ReviewResponse(**review_row, user_name=user_name)

@router.get("/reviews", response_model=PaginatedResponse[ReviewWithCommentsResponse])
def get_reviews(
    sort_by: str = Query(default="created_at", description="정렬 기준: created_at, view_count"),
    sort_order: str = Query(default="desc", description="정렬 순서 (항상 desc)"),
    page: int = Query(default=1, ge=1, description="페이지 번호 (1부터 시작)"),
    limit: int = Query(default=10, ge=1, le=10, description="페이지당 항목 수 (최대 10)")
):
    # 정렬 파라미터 검증
    valid_sort_fields = ["created_at", "view_count"]
    if sort_by not in valid_sort_fields:
        sort_by = "created_at"
    
    # 항상 내림차순 정렬
    sort_desc = True
    
    # 최적화된 총 개수 조회
    count_response = supabase.table("review").select("id", count="exact").execute()
    total_count = count_response.count if hasattr(count_response, 'count') else len(count_response.data)
    
    # 페이지네이션을 적용한 리뷰 데이터 조회
    offset = get_offset(page, limit)
    reviews = supabase.table("review").select("*").order(sort_by, desc=sort_desc).range(offset, offset + limit - 1).execute().data
    
    # 해당 리뷰들의 댓글만 조회
    review_ids = [r["id"] for r in reviews]
    if review_ids:
        comments = supabase.table("review_comment").select("*").in_("review_id", review_ids).order("created_at").execute().data
    else:
        comments = []
    
    # N+1 사용자 조회 문제 해결 - 리뷰 작성자와 댓글 작성자 한 번에 조회
    all_user_ids = set()
    for r in reviews:
        if r.get("user_id"):
            all_user_ids.add(r["user_id"])
    for c in comments:
        if c.get("user_id"):
            all_user_ids.add(c["user_id"])
    
    users_data = {}
    if all_user_ids:
        all_users = supabase.table("user").select("id, username").in_("id", list(all_user_ids)).execute().data
        for user_row in all_users:
            users_data[user_row["id"]] = user_row["username"]
    
    reviews_dict = {}
    for r in reviews:
        user_name = users_data.get(r.get("user_id"), "알수없음")
        reviews_dict[r["id"]] = ReviewWithCommentsResponse(**r, user_name=user_name, comments=[])
    
    # 댓글 추가
    for c in comments:
        if c["review_id"] in reviews_dict:
            comment_user_name = users_data.get(c.get("user_id"), "알수없음")
            reviews_dict[c["review_id"]].comments.append(CommentResponse(**c, user_name=comment_user_name))
    
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
    comments = []
    for c in comments_data:
        comment_user_name = "알수없음"
        if c.get("user_id"):
            user_row = supabase.table("user").select("username").eq("id", c["user_id"]).single().execute().data
            comment_user_name = user_row["username"] if user_row else "알수없음"
        comments.append(CommentResponse(**c, user_name=comment_user_name))
    # 현재 사용자의 투표 상태 확인 (로그인된 경우만)
    user_vote_type = None
    try:
        if hasattr(get_current_user, '__call__'):
            current_user = get_current_user()
            if current_user:
                user_vote = supabase.table("review_vote").select("vote_type").eq("review_id", review_id).eq("user_id", current_user["id"]).execute().data
                if user_vote:
                    user_vote_type = user_vote[0]["vote_type"]
    except:
        pass
    
    user_name = "알수없음"
    if review_row.get("user_id"):
        user_row = supabase.table("user").select("username").eq("id", review_row["user_id"]).single().execute().data
        user_name = user_row["username"] if user_row else "알수없음"
    
    return ReviewWithCommentsResponse(**review_row, user_name=user_name, comments=comments)

@router.post("/reviews/{review_id}/comments", response_model=CommentResponse)
def create_comment(review_id: int, comment: CommentCreate, current_user=Depends(get_current_user)):
    # 리뷰 존재 확인
    review = supabase.table("review").select("id").eq("id", review_id).single().execute().data
    if not review:
        raise HTTPException(status_code=404, detail="Review not found")
    now = datetime.utcnow().isoformat()
    comment_result = supabase.table("review_comment").insert({
        "review_id": review_id,
        "content": comment.content,
        "created_at": now,
        "user_id": current_user["id"]
    }).execute()
    comment_id = comment_result.data[0]["id"]
    comment_row = supabase.table("review_comment").select("*").eq("id", comment_id).single().execute().data
    
    comment_user_name = current_user["username"]
    return CommentResponse(**comment_row, user_name=comment_user_name)

@router.put("/comments/{comment_id}", response_model=CommentResponse)
def update_comment(comment_id: int, comment_update: CommentUpdate, current_user=Depends(get_current_user)):
    # 댓글 존재 및 작성자 확인
    comment_row = supabase.table("review_comment").select("*").eq("id", comment_id).single().execute().data
    if not comment_row:
        raise HTTPException(status_code=404, detail="Comment not found")
    
    if comment_row["user_id"] != current_user["id"]:
        raise HTTPException(status_code=403, detail="You can only update your own comments")
    
    update_fields = {}
    if comment_update.content is not None:
        update_fields["content"] = comment_update.content
    
    if update_fields:
        supabase.table("review_comment").update(update_fields).eq("id", comment_id).execute()
    
    comment_row = supabase.table("review_comment").select("*").eq("id", comment_id).single().execute().data
    
    comment_user_name = current_user["username"]
    return CommentResponse(**comment_row, user_name=comment_user_name)

@router.delete("/comments/{comment_id}")
def delete_comment(comment_id: int, current_user=Depends(get_current_user)):
    # 댓글 존재 및 작성자 확인
    comment_row = supabase.table("review_comment").select("*").eq("id", comment_id).single().execute().data
    if not comment_row:
        raise HTTPException(status_code=404, detail="Comment not found")
    
    if comment_row["user_id"] != current_user["id"]:
        raise HTTPException(status_code=403, detail="You can only delete your own comments")
    
    # 댓글 삭제
    supabase.table("review_comment").delete().eq("id", comment_id).execute()
    return {"msg": "Comment deleted successfully"}

@router.post("/reviews/{review_id}/vote", response_model=VoteResponse)
def vote_review(review_id: int, vote: VoteCreate, current_user=Depends(get_current_user)):
    # 리뷰 존재 확인
    review = supabase.table("review").select("id").eq("id", review_id).single().execute().data
    if not review:
        raise HTTPException(status_code=404, detail="Review not found")
    
    
    # 기존 투표 확인
    existing_vote = supabase.table("review_vote").select("*").eq("review_id", review_id).eq("user_id", current_user["id"]).execute().data
    current_user_vote = None
    
    if existing_vote:
        # 기존 투표가 있으면 처리
        if existing_vote[0]["vote_type"] != vote.vote_type:
            # 다른 타입으로 변경
            supabase.table("review_vote").update({"vote_type": vote.vote_type}).eq("id", existing_vote[0]["id"]).execute()
            current_user_vote = vote.vote_type
        else:
            # 같은 투표를 다시 누르면 삭제 (토글)
            supabase.table("review_vote").delete().eq("id", existing_vote[0]["id"]).execute()
            current_user_vote = None
    else:
        # 새 투표 생성
        now = datetime.utcnow().isoformat()
        supabase.table("review_vote").insert({
            "review_id": review_id,
            "user_id": current_user["id"],
            "vote_type": vote.vote_type,
            "created_at": now
        }).execute()
        current_user_vote = vote.vote_type
    
    # 추천/비추천 수 계산
    votes = supabase.table("review_vote").select("vote_type").eq("review_id", review_id).execute().data
    like_count = sum(1 for v in votes if v["vote_type"] == "like")
    dislike_count = sum(1 for v in votes if v["vote_type"] == "dislike")
    
    # 리뷰 테이블에 추천/비추천 수 업데이트
    supabase.table("review").update({
        "like_count": like_count,
        "dislike_count": dislike_count
    }).eq("id", review_id).execute()
    
    return VoteResponse(
        message="Vote recorded successfully",
        like_count=like_count,
        dislike_count=dislike_count,
        user_vote_type=current_user_vote
    )

@router.get("/reviews/{review_id}/my-vote")
def get_my_review_vote(review_id: int, current_user=Depends(get_current_user)):
    # 리뷰 존재 확인
    review = supabase.table("review").select("id").eq("id", review_id).single().execute().data
    if not review:
        raise HTTPException(status_code=404, detail="Review not found")
    
    # 사용자의 투표 조회
    user_vote = supabase.table("review_vote").select("vote_type").eq("review_id", review_id).eq("user_id", current_user["id"]).execute().data
    
    if user_vote:
        return {"vote_type": user_vote[0]["vote_type"]}
    else:
        return {"vote_type": None}

@router.delete("/reviews/{review_id}/vote")
def remove_review_vote(review_id: int, current_user=Depends(get_current_user)):
    # 리뷰 존재 확인
    review = supabase.table("review").select("id").eq("id", review_id).single().execute().data
    if not review:
        raise HTTPException(status_code=404, detail="Review not found")
    
    user_id = current_user["id"]
    
    # 기존 투표 확인
    existing_vote = supabase.table("review_vote").select("*").eq("review_id", review_id).eq("user_id", user_id).execute().data
    
    if not existing_vote:
        raise HTTPException(status_code=400, detail="No vote found to remove")
    
    # 투표 삭제
    supabase.table("review_vote").delete().eq("review_id", review_id).eq("user_id", user_id).execute()
    
    # 추천/비추천 수 재계산 및 업데이트
    votes = supabase.table("review_vote").select("vote_type").eq("review_id", review_id).execute().data
    like_count = sum(1 for v in votes if v["vote_type"] == "like")
    dislike_count = sum(1 for v in votes if v["vote_type"] == "dislike")
    
    supabase.table("review").update({
        "like_count": like_count,
        "dislike_count": dislike_count
    }).eq("id", review_id).execute()
    
    return {
        "message": "Vote removed successfully",
        "like_count": like_count,
        "dislike_count": dislike_count
    }

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
        # updated_at 필드 추가
        update_fields["updated_at"] = datetime.utcnow().isoformat()
        supabase.table("review").update(update_fields).eq("id", review_id).execute()
    review_row = supabase.table("review").select("*").eq("id", review_id).single().execute().data
    
    user_name = "알수없음"
    if review_row.get("user_id"):
        user_row = supabase.table("user").select("username").eq("id", review_row["user_id"]).single().execute().data
        user_name = user_row["username"] if user_row else "알수없음"
    
    return ReviewResponse(**review_row, user_name=user_name)

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
    # 추천/비추천 삭제
    supabase.table("review_vote").delete().eq("review_id", review_id).execute()
    # 리뷰 삭제
    supabase.table("review").delete().eq("id", review_id).execute()
    return {"msg": "Review deleted successfully"} 