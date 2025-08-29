from fastapi import APIRouter, HTTPException, Depends, Query
from pydantic import BaseModel, Field
from typing import List, Optional
from datetime import datetime
from .db import supabase
from .auth import get_current_user
from .pagination import PaginationParams, PaginatedResponse, create_pagination_info, get_offset
import os

router = APIRouter()

# Pydantic Models
class PhishingSiteCreate(BaseModel):
    url: str = Field(..., description="피싱 의심 사이트 링크")
    reason: str = Field(..., description="사유 (예: '가짜 로그인 페이지', '결제 유도', '이메일 피싱')")
    description: Optional[str] = Field(None, description="자세한 설명 (선택사항)")

class PhishingSiteUpdate(BaseModel):
    url: Optional[str] = None
    reason: Optional[str] = None
    description: Optional[str] = None
    status: Optional[str] = Field(None, description="상태 (검토중, 확인됨, 무시됨)")

class PhishingSiteResponse(BaseModel):
    id: int
    url: str
    reason: str
    description: Optional[str]
    status: str
    created_at: str
    view_count: int = 0
    like_count: int = 0
    dislike_count: int = 0
    user_id: Optional[int]

class VoteCreate(BaseModel):
    vote_type: str = Field(..., description="추천/비추천 ('like' 또는 'dislike')")

class VoteResponse(BaseModel):
    message: str
    like_count: int
    dislike_count: int
    user_vote_type: Optional[str] = None

class CommentCreate(BaseModel):
    content: str = Field(..., description="댓글 내용")

class CommentUpdate(BaseModel):
    content: str = Field(..., description="수정할 댓글 내용")

class CommentResponse(BaseModel):
    id: int
    phishing_site_id: int
    user_id: int
    user_name: str
    content: str
    created_at: str
    updated_at: str

class PhishingSiteWithCommentsResponse(BaseModel):
    id: int
    url: str
    reason: str
    description: Optional[str]
    status: str
    created_at: str
    view_count: int = 0
    like_count: int = 0
    dislike_count: int = 0
    user_id: Optional[int]
    comments: List[CommentResponse]

# API Endpoints
@router.post("/phishing-sites", response_model=PhishingSiteResponse)
def create_phishing_site(phishing_site: PhishingSiteCreate, current_user=Depends(get_current_user)):
    now = datetime.utcnow().isoformat()
    result = supabase.table("phishing_site").insert({
        "url": phishing_site.url,
        "reason": phishing_site.reason,
        "description": phishing_site.description,
        "status": "검토중",
        "created_at": now,
        "view_count": 0,
        "like_count": 0,
        "dislike_count": 0,
        "user_id": current_user["id"]
    }).execute()
    phishing_site_id = result.data[0]["id"]
    site_row = supabase.table("phishing_site").select("*").eq("id", phishing_site_id).single().execute().data
    return PhishingSiteResponse(**site_row)

@router.get("/phishing-sites", response_model=PaginatedResponse[PhishingSiteResponse])
def get_phishing_sites(
    status: Optional[str] = None,
    page: int = Query(default=1, ge=1, description="페이지 번호 (1부터 시작)"),
    limit: int = Query(default=10, ge=1, le=10, description="페이지당 항목 수 (최대 10)")
):
    # 총 개수 조회
    if status:
        total_count = len(supabase.table("phishing_site").select("id").eq("status", status).execute().data)
        sites = supabase.table("phishing_site").select("*").eq("status", status).order("created_at", desc=True).range(get_offset(page, limit), get_offset(page, limit) + limit - 1).execute().data
    else:
        total_count = len(supabase.table("phishing_site").select("id").execute().data)
        sites = supabase.table("phishing_site").select("*").order("created_at", desc=True).range(get_offset(page, limit), get_offset(page, limit) + limit - 1).execute().data
    
    sites_data = [PhishingSiteResponse(**site) for site in sites]
    pagination_info = create_pagination_info(page, limit, total_count)
    return PaginatedResponse(data=sites_data, pagination=pagination_info)

@router.get("/phishing-sites/{site_id}", response_model=PhishingSiteResponse)
def get_phishing_site(site_id: int):
    site_row = supabase.table("phishing_site").select("*").eq("id", site_id).single().execute().data
    if not site_row:
        raise HTTPException(status_code=404, detail="Phishing site not found")
    
    # 조회수 증가
    current_view_count = site_row.get("view_count", 0)
    supabase.table("phishing_site").update({
        "view_count": current_view_count + 1
    }).eq("id", site_id).execute()
    
    # 업데이트된 view_count를 반영
    site_row["view_count"] = current_view_count + 1
    
    return PhishingSiteResponse(**site_row)

@router.put("/phishing-sites/{site_id}", response_model=PhishingSiteResponse)
def update_phishing_site(site_id: int, site_update: PhishingSiteUpdate):
    existing_site = supabase.table("phishing_site").select("*").eq("id", site_id).single().execute().data
    if not existing_site:
        raise HTTPException(status_code=404, detail="Phishing site not found")
    update_data = {}
    if site_update.url is not None:
        update_data["url"] = site_update.url
    if site_update.reason is not None:
        update_data["reason"] = site_update.reason
    if site_update.description is not None:
        update_data["description"] = site_update.description
    if site_update.status is not None:
        update_data["status"] = site_update.status
    if not update_data:
        raise HTTPException(status_code=400, detail="No update fields provided")
    try:
        supabase.table("phishing_site").update(update_data).eq("id", site_id).execute()
        site_row = supabase.table("phishing_site").select("*").eq("id", site_id).single().execute().data
        if not site_row:
            raise HTTPException(status_code=404, detail="Phishing site not found after update")
        return PhishingSiteResponse(**site_row)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to update phishing site: {str(e)}")

@router.delete("/phishing-sites/{site_id}")
def delete_phishing_site(site_id: int, current_user=Depends(get_current_user)):
    site_row = supabase.table("phishing_site").select("*").eq("id", site_id).single().execute().data
    if not site_row:
        raise HTTPException(status_code=404, detail="Phishing site not found")
    
    # 작성자 권한 확인
    if site_row["user_id"] != current_user["id"]:
        raise HTTPException(status_code=403, detail="You can only delete your own phishing site reports")
    try:
        # 댓글 먼저 삭제
        supabase.table("phishing_comment").delete().eq("phishing_site_id", site_id).execute()
        # 투표 기록 삭제
        supabase.table("phishing_vote").delete().eq("phishing_site_id", site_id).execute()
        # 피싱사이트 삭제
        supabase.table("phishing_site").delete().eq("id", site_id).execute()
        return {"msg": "Phishing site deleted successfully"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to delete phishing site: {str(e)}")

@router.post("/phishing-sites/{site_id}/vote", response_model=VoteResponse)
def vote_phishing_site(site_id: int, vote: VoteCreate, current_user=Depends(get_current_user)):
    # 피싱사이트 존재 확인
    site_row = supabase.table("phishing_site").select("*").eq("id", site_id).single().execute().data
    if not site_row:
        raise HTTPException(status_code=404, detail="Phishing site not found")
    
    # vote_type 검증
    if vote.vote_type not in ["like", "dislike"]:
        raise HTTPException(status_code=400, detail="vote_type must be 'like' or 'dislike'")
    
    user_id = current_user["id"]
    now = datetime.utcnow().isoformat()
    
    try:
        # 기존 투표 확인
        existing_vote = supabase.table("phishing_vote").select("*").eq("phishing_site_id", site_id).eq("user_id", user_id).execute().data
        current_user_vote = None
        
        if existing_vote:
            old_vote_type = existing_vote[0]["vote_type"]
            if old_vote_type == vote.vote_type:
                # 같은 투표를 다시 누르면 삭제 (토글)
                supabase.table("phishing_vote").delete().eq("phishing_site_id", site_id).eq("user_id", user_id).execute()
                current_user_vote = None
                
                # 카운트 감소
                if old_vote_type == "like":
                    supabase.table("phishing_site").update({
                        "like_count": max(0, site_row.get("like_count", 0) - 1)
                    }).eq("id", site_id).execute()
                else:
                    supabase.table("phishing_site").update({
                        "dislike_count": max(0, site_row.get("dislike_count", 0) - 1)
                    }).eq("id", site_id).execute()
            else:
                # 다른 타입으로 변경
                supabase.table("phishing_vote").update({"vote_type": vote.vote_type}).eq("id", existing_vote[0]["id"]).execute()
                current_user_vote = vote.vote_type
                
                # 이전 투표 카운트 감소
                if old_vote_type == "like":
                    supabase.table("phishing_site").update({
                        "like_count": max(0, site_row.get("like_count", 0) - 1)
                    }).eq("id", site_id).execute()
                else:
                    supabase.table("phishing_site").update({
                        "dislike_count": max(0, site_row.get("dislike_count", 0) - 1)
                    }).eq("id", site_id).execute()
                
                # 새 투표 카운트 증가
                site_row = supabase.table("phishing_site").select("*").eq("id", site_id).single().execute().data
                if vote.vote_type == "like":
                    supabase.table("phishing_site").update({
                        "like_count": site_row.get("like_count", 0) + 1
                    }).eq("id", site_id).execute()
                else:
                    supabase.table("phishing_site").update({
                        "dislike_count": site_row.get("dislike_count", 0) + 1
                    }).eq("id", site_id).execute()
        else:
            # 새 투표 생성
            supabase.table("phishing_vote").insert({
                "phishing_site_id": site_id,
                "user_id": user_id,
                "vote_type": vote.vote_type,
                "created_at": now
            }).execute()
            current_user_vote = vote.vote_type
            
            # 카운트 증가
            if vote.vote_type == "like":
                supabase.table("phishing_site").update({
                    "like_count": site_row.get("like_count", 0) + 1
                }).eq("id", site_id).execute()
            else:
                supabase.table("phishing_site").update({
                    "dislike_count": site_row.get("dislike_count", 0) + 1
                }).eq("id", site_id).execute()
        
        # 업데이트된 카운트 조회
        updated_site = supabase.table("phishing_site").select("like_count, dislike_count").eq("id", site_id).single().execute().data
        
        return VoteResponse(
            message="Vote recorded successfully",
            like_count=updated_site.get("like_count", 0),
            dislike_count=updated_site.get("dislike_count", 0),
            user_vote_type=current_user_vote
        )
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to vote: {str(e)}")

@router.delete("/phishing-sites/{site_id}/vote")
def remove_vote_phishing_site(site_id: int, current_user=Depends(get_current_user)):
    # 피싱사이트 존재 확인
    site_row = supabase.table("phishing_site").select("*").eq("id", site_id).single().execute().data
    if not site_row:
        raise HTTPException(status_code=404, detail="Phishing site not found")
    
    user_id = current_user["id"]
    
    try:
        # 기존 투표 확인
        existing_vote = supabase.table("phishing_vote").select("*").eq("phishing_site_id", site_id).eq("user_id", user_id).single().execute().data
        
        if not existing_vote:
            raise HTTPException(status_code=400, detail="No vote found to remove")
        
        old_vote_type = existing_vote["vote_type"]
        
        # 투표 삭제
        supabase.table("phishing_vote").delete().eq("phishing_site_id", site_id).eq("user_id", user_id).execute()
        
        # 카운트 감소
        if old_vote_type == "like":
            supabase.table("phishing_site").update({
                "like_count": max(0, site_row.get("like_count", 0) - 1)
            }).eq("id", site_id).execute()
        else:
            supabase.table("phishing_site").update({
                "dislike_count": max(0, site_row.get("dislike_count", 0) - 1)
            }).eq("id", site_id).execute()
        
        return {"msg": "Vote removed successfully"}
        
    except Exception as e:
        if "No vote found" in str(e):
            raise e
        raise HTTPException(status_code=500, detail=f"Failed to remove vote: {str(e)}")

@router.get("/phishing-sites/{site_id}/my-vote")
def get_my_vote_phishing_site(site_id: int, current_user=Depends(get_current_user)):
    # 피싱사이트 존재 확인
    try:
        site_check = supabase.table("phishing_site").select("id").eq("id", site_id).execute().data
        if not site_check:
            raise HTTPException(status_code=404, detail="Phishing site not found")
    except Exception as e:
        raise HTTPException(status_code=404, detail="Phishing site not found")
    
    user_id = current_user["id"]
    
    try:
        vote_result = supabase.table("phishing_vote").select("vote_type").eq("phishing_site_id", site_id).eq("user_id", user_id).execute()
        if vote_result.data and len(vote_result.data) > 0:
            return {"vote_type": vote_result.data[0]["vote_type"]}
        else:
            return {"vote_type": None}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to get vote: {str(e)}")

# 댓글 관련 API들
@router.post("/phishing-sites/{site_id}/comments", response_model=CommentResponse)
def create_phishing_comment(site_id: int, comment: CommentCreate, current_user=Depends(get_current_user)):
    # 피싱사이트 존재 확인
    if not supabase.table("phishing_site").select("id").eq("id", site_id).single().execute().data:
        raise HTTPException(status_code=404, detail="Phishing site not found")
    
    now = datetime.utcnow().isoformat()
    user_id = current_user["id"]
    user_name = current_user["username"]
    
    try:
        comment_result = supabase.table("phishing_comment").insert({
            "phishing_site_id": site_id,
            "user_id": user_id,
            "content": comment.content,
            "created_at": now,
            "updated_at": now
        }).execute()
        
        comment_id = comment_result.data[0]["id"]
        comment_row = supabase.table("phishing_comment").select("*").eq("id", comment_id).single().execute().data
        
        return CommentResponse(
            id=comment_row["id"],
            phishing_site_id=comment_row["phishing_site_id"],
            user_id=comment_row["user_id"],
            user_name=user_name,
            content=comment_row["content"],
            created_at=comment_row["created_at"],
            updated_at=comment_row["updated_at"]
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to create comment: {str(e)}")

@router.get("/phishing-sites/{site_id}/comments", response_model=List[CommentResponse])
def get_phishing_comments(site_id: int):
    # 피싱사이트 존재 확인
    if not supabase.table("phishing_site").select("id").eq("id", site_id).single().execute().data:
        raise HTTPException(status_code=404, detail="Phishing site not found")
    
    try:
        comments_data = supabase.table("phishing_comment").select("*").eq("phishing_site_id", site_id).order("created_at").execute().data
        comments = []
        
        for comment_row in comments_data:
            # 사용자명 조회
            user_row = supabase.table("user").select("username").eq("id", comment_row["user_id"]).single().execute().data
            user_name = user_row["username"] if user_row else "알 수 없음"
            
            comments.append(CommentResponse(
                id=comment_row["id"],
                phishing_site_id=comment_row["phishing_site_id"],
                user_id=comment_row["user_id"],
                user_name=user_name,
                content=comment_row["content"],
                created_at=comment_row["created_at"],
                updated_at=comment_row["updated_at"]
            ))
        
        return comments
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to get comments: {str(e)}")

@router.get("/phishing-sites/{site_id}/with-comments", response_model=PhishingSiteWithCommentsResponse)
def get_phishing_site_with_comments(site_id: int):
    # 피싱사이트 데이터 조회 및 조회수 증가
    site_row = supabase.table("phishing_site").select("*").eq("id", site_id).single().execute().data
    if not site_row:
        raise HTTPException(status_code=404, detail="Phishing site not found")
    
    # 조회수 증가
    current_view_count = site_row.get("view_count", 0)
    supabase.table("phishing_site").update({
        "view_count": current_view_count + 1
    }).eq("id", site_id).execute()
    site_row["view_count"] = current_view_count + 1
    
    # 댓글 조회
    comments_data = supabase.table("phishing_comment").select("*").eq("phishing_site_id", site_id).order("created_at").execute().data
    comments = []
    
    for comment_row in comments_data:
        user_row = supabase.table("user").select("username").eq("id", comment_row["user_id"]).single().execute().data
        user_name = user_row["username"] if user_row else "알 수 없음"
        
        comments.append(CommentResponse(
            id=comment_row["id"],
            phishing_site_id=comment_row["phishing_site_id"],
            user_id=comment_row["user_id"],
            user_name=user_name,
            content=comment_row["content"],
            created_at=comment_row["created_at"],
            updated_at=comment_row["updated_at"]
        ))
    
    return PhishingSiteWithCommentsResponse(
        id=site_row["id"],
        url=site_row["url"],
        reason=site_row["reason"],
        description=site_row["description"],
        status=site_row["status"],
        created_at=site_row["created_at"],
        view_count=site_row["view_count"],
        like_count=site_row.get("like_count", 0),
        dislike_count=site_row.get("dislike_count", 0),
        comments=comments
    )

@router.put("/phishing-sites/{site_id}/comments/{comment_id}", response_model=CommentResponse)
def update_phishing_comment(site_id: int, comment_id: int, comment_update: CommentUpdate, current_user=Depends(get_current_user)):
    # 댓글 존재 확인
    comment_row = supabase.table("phishing_comment").select("*").eq("id", comment_id).eq("phishing_site_id", site_id).single().execute().data
    if not comment_row:
        raise HTTPException(status_code=404, detail="Comment not found")
    
    # 작성자 확인
    if comment_row["user_id"] != current_user["id"]:
        raise HTTPException(status_code=403, detail="You can only update your own comments")
    
    now = datetime.utcnow().isoformat()
    
    try:
        supabase.table("phishing_comment").update({
            "content": comment_update.content,
            "updated_at": now
        }).eq("id", comment_id).execute()
        
        updated_comment = supabase.table("phishing_comment").select("*").eq("id", comment_id).single().execute().data
        
        return CommentResponse(
            id=updated_comment["id"],
            phishing_site_id=updated_comment["phishing_site_id"],
            user_id=updated_comment["user_id"],
            user_name=current_user["username"],
            content=updated_comment["content"],
            created_at=updated_comment["created_at"],
            updated_at=updated_comment["updated_at"]
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to update comment: {str(e)}")

@router.delete("/phishing-sites/{site_id}/comments/{comment_id}")
def delete_phishing_comment(site_id: int, comment_id: int, current_user=Depends(get_current_user)):
    # 댓글 존재 확인
    comment_row = supabase.table("phishing_comment").select("*").eq("id", comment_id).eq("phishing_site_id", site_id).single().execute().data
    if not comment_row:
        raise HTTPException(status_code=404, detail="Comment not found")
    
    # 작성자 확인
    if comment_row["user_id"] != current_user["id"]:
        raise HTTPException(status_code=403, detail="You can only delete your own comments")
    
    try:
        supabase.table("phishing_comment").delete().eq("id", comment_id).execute()
        return {"msg": "Comment deleted successfully"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to delete comment: {str(e)}") 