from fastapi import APIRouter, HTTPException, Depends, Response, Query
from pydantic import BaseModel, Field
from typing import List, Optional
from datetime import datetime
from .auth import get_current_user
from .db import supabase
from .pagination import PaginationParams, PaginatedResponse, create_pagination_info, get_offset
import os
import json

router = APIRouter()

class PostCreate(BaseModel):
    title: str
    category: str
    content: dict
    tags: List[str] = []

class PostUpdate(BaseModel):
    title: Optional[str]
    category: Optional[str]
    content: Optional[dict]
    tags: Optional[List[str]]

class PostResponse(BaseModel):
    id: int
    title: str
    category: str
    content: dict
    tags: List[str]
    created_at: str
    updated_at: str
    user_id: int
    user_name: str
    view_count: int = 0
    like_count: int = 0
    dislike_count: int = 0

class VoteCreate(BaseModel):
    vote_type: str = Field(..., description="추천/비추천 ('like' 또는 'dislike')")

class VoteResponse(BaseModel):
    message: str
    like_count: int
    dislike_count: int
    user_vote_type: Optional[str] = None

class PostCommentCreate(BaseModel):
    content: str = Field(..., description="댓글 내용")

class PostCommentUpdate(BaseModel):
    content: str = Field(..., description="수정할 댓글 내용")

class PostCommentResponse(BaseModel):
    id: int
    post_id: int
    user_id: int
    user_name: str
    content: str
    created_at: str
    updated_at: str

class PostWithCommentsResponse(BaseModel):
    id: int
    title: str
    category: str
    content: dict
    tags: List[str]
    created_at: str
    updated_at: str
    user_id: int
    user_name: str
    view_count: int = 0
    like_count: int = 0
    dislike_count: int = 0
    comments: List[PostCommentResponse]

@router.post("/posts", response_model=PostResponse)
def create_post(post: PostCreate, current_user=Depends(get_current_user)):
    now = datetime.utcnow().isoformat()
    # Post 생성
    post_result = supabase.table("post").insert({
        "title": post.title,
        "category": post.category,
        "content": json.dumps(post.content),
        "created_at": now,
        "updated_at": now,
        "user_id": current_user["id"],
        "user_name": current_user["username"],
        "view_count": 0,
        "like_count": 0,
        "dislike_count": 0
    }).execute()
    post_id = post_result.data[0]["id"]
    # Tags 생성
    for tag_name in post.tags:
        supabase.table("tag").insert({"name": tag_name, "post_id": post_id}).execute()
    # 생성된 post + 작성자 username 조회
    post_row = supabase.table("post").select("*").eq("id", post_id).single().execute().data
    tags = [row["name"] for row in supabase.table("tag").select("name").eq("post_id", post_id).execute().data]
    return PostResponse(
        id=post_row["id"],
        title=post_row["title"],
        category=post_row["category"],
        content=json.loads(post_row["content"]),
        tags=tags,
        created_at=post_row["created_at"],
        updated_at=post_row["updated_at"],
        user_id=post_row["user_id"],
        user_name=post_row["user_name"]
    )

@router.get("/posts", response_model=PaginatedResponse[PostResponse])
def get_posts(
    category: Optional[str] = None, 
    tag: Optional[str] = None, 
    type: Optional[str] = None,
    sort_by: str = Query(default="created_at", description="정렬 기준: created_at, view_count, like_count, dislike_count"),
    sort_order: str = Query(default="desc", description="정렬 순서: desc, asc"),
    page: int = Query(default=1, ge=1, description="페이지 번호 (1부터 시작)"),
    limit: int = Query(default=10, ge=1, le=10, description="페이지당 항목 수 (최대 10)")
):
    category_map = {
        '자유게시판': 'free',
        'free': 'free',
        'Free': 'free',
        'FREE': 'free',
    }
    db_category = None
    if category:
        db_category = category_map.get(category, category)
    
    # 정렬 파라미터 검증
    valid_sort_fields = ["created_at", "updated_at", "view_count", "like_count", "dislike_count"]
    if sort_by not in valid_sort_fields:
        sort_by = "created_at"
    
    sort_desc = (sort_order.lower() == "desc")
    
    # 총 개수 조회
    if tag:
        total_count = len(supabase.table("post").select("id", "tag(name)").eq("tag.name", tag).execute().data)
        post_rows = supabase.table("post").select("*", "tag(name)").eq("tag.name", tag).order(sort_by, desc=sort_desc).range(get_offset(page, limit), get_offset(page, limit) + limit - 1).execute().data
    elif db_category:
        total_count = len(supabase.table("post").select("id").eq("category", db_category).execute().data)
        post_rows = supabase.table("post").select("*").eq("category", db_category).order(sort_by, desc=sort_desc).range(get_offset(page, limit), get_offset(page, limit) + limit - 1).execute().data
    else:
        total_count = len(supabase.table("post").select("id").execute().data)
        post_rows = supabase.table("post").select("*").order(sort_by, desc=sort_desc).range(get_offset(page, limit), get_offset(page, limit) + limit - 1).execute().data
    
    posts = []
    for post_row in post_rows:
        tags = [row["name"] for row in supabase.table("tag").select("name").eq("post_id", post_row["id"]).execute().data]
        user_name = post_row.get("user_name")
        if not user_name and post_row.get("user_id"):
            user_row = supabase.table("user").select("username").eq("id", post_row["user_id"]).single().execute().data
            user_name = user_row["username"] if user_row else "알수없음"
        elif not user_name:
            user_name = "알수없음"
        posts.append(PostResponse(
            id=post_row["id"],
            title=post_row["title"],
            category=post_row["category"],
            content=json.loads(post_row["content"]),
            tags=tags,
            created_at=post_row["created_at"],
            updated_at=post_row["updated_at"],
            user_id=post_row["user_id"],
            user_name=user_name,
            view_count=post_row.get("view_count", 0),
            like_count=post_row.get("like_count", 0),
            dislike_count=post_row.get("dislike_count", 0)
        ))
    
    pagination_info = create_pagination_info(page, limit, total_count)
    return PaginatedResponse(data=posts, pagination=pagination_info)

@router.get("/posts/{post_id}", response_model=PostResponse)
def get_post(post_id: int):
    post_row = supabase.table("post").select("*").eq("id", post_id).single().execute().data
    if not post_row:
        raise HTTPException(status_code=404, detail="Post not found")
    
    # 조회수 증가
    current_view_count = post_row.get("view_count", 0)
    supabase.table("post").update({
        "view_count": current_view_count + 1
    }).eq("id", post_id).execute()
    
    # 업데이트된 view_count를 반영
    post_row["view_count"] = current_view_count + 1
    
    tags = [row["name"] for row in supabase.table("tag").select("name").eq("post_id", post_id).execute().data]
    user_name = post_row.get("user_name")
    if not user_name and post_row.get("user_id"):
        user_row = supabase.table("user").select("username").eq("id", post_row["user_id"]).single().execute().data
        user_name = user_row["username"] if user_row else "알수없음"
    elif not user_name:
        user_name = "알수없음"
        
    return PostResponse(
        id=post_row["id"],
        title=post_row["title"],
        category=post_row["category"],
        content=json.loads(post_row["content"]),
        tags=tags,
        created_at=post_row["created_at"],
        updated_at=post_row["updated_at"],
        user_id=post_row["user_id"],
        user_name=user_name,
        view_count=post_row["view_count"],
        like_count=post_row.get("like_count", 0),
        dislike_count=post_row.get("dislike_count", 0)
    )

@router.put("/posts/{post_id}", response_model=PostResponse)
def update_post(post_id: int, post_update: PostUpdate, current_user=Depends(get_current_user)):
    # 게시물 존재 및 작성자 확인
    post_row = supabase.table("post").select("*").eq("id", post_id).single().execute().data
    if not post_row:
        raise HTTPException(status_code=404, detail="Post not found")
    
    if post_row["user_id"] != current_user["id"]:
        raise HTTPException(status_code=403, detail="You can only update your own posts")
    
    update_fields = {}
    if post_update.title is not None:
        update_fields["title"] = post_update.title
    if post_update.category is not None:
        update_fields["category"] = post_update.category
    if post_update.content is not None:
        update_fields["content"] = json.dumps(post_update.content)
    if update_fields:
        update_fields["updated_at"] = datetime.utcnow().isoformat()
        supabase.table("post").update(update_fields).eq("id", post_id).execute()
    if post_update.tags is not None:
        supabase.table("tag").delete().eq("post_id", post_id).execute()
        for tag_name in post_update.tags:
            supabase.table("tag").insert({"name": tag_name, "post_id": post_id}).execute()
    return get_post(post_id)

@router.delete("/posts/{post_id}")
def delete_post(post_id: int, current_user=Depends(get_current_user)):
    # 게시물 존재 및 작성자 확인
    post_row = supabase.table("post").select("*").eq("id", post_id).single().execute().data
    if not post_row:
        raise HTTPException(status_code=404, detail="Post not found")
    
    if post_row["user_id"] != current_user["id"]:
        raise HTTPException(status_code=403, detail="You can only delete your own posts")
    
    # 댓글 먼저 삭제
    supabase.table("post_comment").delete().eq("post_id", post_id).execute()
    # 투표 기록 삭제
    supabase.table("post_vote").delete().eq("post_id", post_id).execute()
    # 태그 삭제
    supabase.table("tag").delete().eq("post_id", post_id).execute()
    # 게시글 삭제
    supabase.table("post").delete().eq("id", post_id).execute()
    return {"msg": "Post deleted successfully"}

@router.post("/posts/{post_id}/vote", response_model=VoteResponse)
def vote_post(post_id: int, vote: VoteCreate, current_user=Depends(get_current_user)):
    # 게시글 존재 확인
    post_row = supabase.table("post").select("*").eq("id", post_id).single().execute().data
    if not post_row:
        raise HTTPException(status_code=404, detail="Post not found")
    
    # vote_type 검증
    if vote.vote_type not in ["like", "dislike"]:
        raise HTTPException(status_code=400, detail="vote_type must be 'like' or 'dislike'")
    
    user_id = current_user["id"]
    now = datetime.utcnow().isoformat()
    
    try:
        # 기존 투표 확인
        existing_vote = supabase.table("post_vote").select("*").eq("post_id", post_id).eq("user_id", user_id).execute().data
        current_user_vote = None
        
        if existing_vote:
            old_vote_type = existing_vote[0]["vote_type"]
            if old_vote_type == vote.vote_type:
                # 같은 투표를 다시 누르면 삭제 (토글)
                supabase.table("post_vote").delete().eq("post_id", post_id).eq("user_id", user_id).execute()
                current_user_vote = None
                
                # 카운트 감소
                if old_vote_type == "like":
                    supabase.table("post").update({
                        "like_count": max(0, post_row.get("like_count", 0) - 1)
                    }).eq("id", post_id).execute()
                else:
                    supabase.table("post").update({
                        "dislike_count": max(0, post_row.get("dislike_count", 0) - 1)
                    }).eq("id", post_id).execute()
            else:
                # 다른 타입으로 변경
                supabase.table("post_vote").update({"vote_type": vote.vote_type}).eq("id", existing_vote[0]["id"]).execute()
                current_user_vote = vote.vote_type
                
                # 이전 투표 카운트 감소
                if old_vote_type == "like":
                    supabase.table("post").update({
                        "like_count": max(0, post_row.get("like_count", 0) - 1)
                    }).eq("id", post_id).execute()
                else:
                    supabase.table("post").update({
                        "dislike_count": max(0, post_row.get("dislike_count", 0) - 1)
                    }).eq("id", post_id).execute()
                
                # 새 투표 카운트 증가
                post_row = supabase.table("post").select("*").eq("id", post_id).single().execute().data
                if vote.vote_type == "like":
                    supabase.table("post").update({
                        "like_count": post_row.get("like_count", 0) + 1
                    }).eq("id", post_id).execute()
                else:
                    supabase.table("post").update({
                        "dislike_count": post_row.get("dislike_count", 0) + 1
                    }).eq("id", post_id).execute()
        else:
            # 새 투표 생성
            supabase.table("post_vote").insert({
                "post_id": post_id,
                "user_id": user_id,
                "vote_type": vote.vote_type,
                "created_at": now
            }).execute()
            current_user_vote = vote.vote_type
            
            # 카운트 증가
            if vote.vote_type == "like":
                supabase.table("post").update({
                    "like_count": post_row.get("like_count", 0) + 1
                }).eq("id", post_id).execute()
            else:
                supabase.table("post").update({
                    "dislike_count": post_row.get("dislike_count", 0) + 1
                }).eq("id", post_id).execute()
        
        # 업데이트된 카운트 조회
        updated_post = supabase.table("post").select("like_count, dislike_count").eq("id", post_id).single().execute().data
        
        return VoteResponse(
            message="Vote recorded successfully",
            like_count=updated_post.get("like_count", 0),
            dislike_count=updated_post.get("dislike_count", 0),
            user_vote_type=current_user_vote
        )
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to vote: {str(e)}")

@router.delete("/posts/{post_id}/vote")
def remove_vote_post(post_id: int, current_user=Depends(get_current_user)):
    # 게시글 존재 확인
    post_row = supabase.table("post").select("*").eq("id", post_id).single().execute().data
    if not post_row:
        raise HTTPException(status_code=404, detail="Post not found")
    
    user_id = current_user["id"]
    
    try:
        # 기존 투표 확인
        existing_vote = supabase.table("post_vote").select("*").eq("post_id", post_id).eq("user_id", user_id).single().execute().data
        
        if not existing_vote:
            raise HTTPException(status_code=400, detail="No vote found to remove")
        
        old_vote_type = existing_vote["vote_type"]
        
        # 투표 삭제
        supabase.table("post_vote").delete().eq("post_id", post_id).eq("user_id", user_id).execute()
        
        # 카운트 감소
        if old_vote_type == "like":
            supabase.table("post").update({
                "like_count": max(0, post_row.get("like_count", 0) - 1)
            }).eq("id", post_id).execute()
        else:
            supabase.table("post").update({
                "dislike_count": max(0, post_row.get("dislike_count", 0) - 1)
            }).eq("id", post_id).execute()
        
        return {"msg": "Vote removed successfully"}
        
    except Exception as e:
        if "No vote found" in str(e):
            raise e
        raise HTTPException(status_code=500, detail=f"Failed to remove vote: {str(e)}")

@router.get("/posts/{post_id}/my-vote")
def get_my_vote_post(post_id: int, current_user=Depends(get_current_user)):
    # 게시글 존재 확인
    if not supabase.table("post").select("id").eq("id", post_id).single().execute().data:
        raise HTTPException(status_code=404, detail="Post not found")
    
    user_id = current_user["id"]
    
    try:
        vote = supabase.table("post_vote").select("vote_type").eq("post_id", post_id).eq("user_id", user_id).execute().data
        if vote:
            return {"vote_type": vote[0]["vote_type"]}
        else:
            return {"vote_type": None}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to get vote: {str(e)}")

# 댓글 관련 API들
@router.post("/posts/{post_id}/comments", response_model=PostCommentResponse)
def create_post_comment(post_id: int, comment: PostCommentCreate, current_user=Depends(get_current_user)):
    # 게시글 존재 확인
    if not supabase.table("post").select("id").eq("id", post_id).single().execute().data:
        raise HTTPException(status_code=404, detail="Post not found")
    
    now = datetime.utcnow().isoformat()
    user_id = current_user["id"]
    user_name = current_user["username"]
    
    try:
        comment_result = supabase.table("post_comment").insert({
            "post_id": post_id,
            "user_id": user_id,
            "content": comment.content,
            "created_at": now,
            "updated_at": now
        }).execute()
        
        comment_id = comment_result.data[0]["id"]
        comment_row = supabase.table("post_comment").select("*").eq("id", comment_id).single().execute().data
        
        return PostCommentResponse(
            id=comment_row["id"],
            post_id=comment_row["post_id"],
            user_id=comment_row["user_id"],
            user_name=user_name,
            content=comment_row["content"],
            created_at=comment_row["created_at"],
            updated_at=comment_row["updated_at"]
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to create comment: {str(e)}")

@router.get("/posts/{post_id}/comments", response_model=List[PostCommentResponse])
def get_post_comments(post_id: int):
    # 게시글 존재 확인
    if not supabase.table("post").select("id").eq("id", post_id).single().execute().data:
        raise HTTPException(status_code=404, detail="Post not found")
    
    try:
        comments_data = supabase.table("post_comment").select("*").eq("post_id", post_id).order("created_at").execute().data
        comments = []
        
        for comment_row in comments_data:
            # 사용자명 조회
            user_row = supabase.table("user").select("username").eq("id", comment_row["user_id"]).single().execute().data
            user_name = user_row["username"] if user_row else "알수없음"
            
            comments.append(PostCommentResponse(
                id=comment_row["id"],
                post_id=comment_row["post_id"],
                user_id=comment_row["user_id"],
                user_name=user_name,
                content=comment_row["content"],
                created_at=comment_row["created_at"],
                updated_at=comment_row["updated_at"]
            ))
        
        return comments
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to get comments: {str(e)}")

@router.get("/posts/{post_id}/with-comments", response_model=PostWithCommentsResponse)
def get_post_with_comments(post_id: int):
    # 게시글 데이터 조회 및 조회수 증가
    post_row = supabase.table("post").select("*").eq("id", post_id).single().execute().data
    if not post_row:
        raise HTTPException(status_code=404, detail="Post not found")
    
    # 조회수 증가
    current_view_count = post_row.get("view_count", 0)
    supabase.table("post").update({
        "view_count": current_view_count + 1
    }).eq("id", post_id).execute()
    post_row["view_count"] = current_view_count + 1
    
    # 태그 조회
    tags = [row["name"] for row in supabase.table("tag").select("name").eq("post_id", post_id).execute().data]
    
    # 댓글 조회
    comments_data = supabase.table("post_comment").select("*").eq("post_id", post_id).order("created_at").execute().data
    comments = []
    
    for comment_row in comments_data:
        user_row = supabase.table("user").select("username").eq("id", comment_row["user_id"]).single().execute().data
        user_name = user_row["username"] if user_row else "알 수 없음"
        
        comments.append(PostCommentResponse(
            id=comment_row["id"],
            post_id=comment_row["post_id"],
            user_id=comment_row["user_id"],
            user_name=user_name,
            content=comment_row["content"],
            created_at=comment_row["created_at"],
            updated_at=comment_row["updated_at"]
        ))
    
    post_user_name = post_row.get("user_name")
    if not post_user_name and post_row.get("user_id"):
        user_row = supabase.table("user").select("username").eq("id", post_row["user_id"]).single().execute().data
        post_user_name = user_row["username"] if user_row else "알수없음"
    elif not post_user_name:
        post_user_name = "알수없음"
        
    return PostWithCommentsResponse(
        id=post_row["id"],
        title=post_row["title"],
        category=post_row["category"],
        content=json.loads(post_row["content"]),
        tags=tags,
        created_at=post_row["created_at"],
        updated_at=post_row["updated_at"],
        user_id=post_row["user_id"],
        user_name=post_user_name,
        view_count=post_row["view_count"],
        like_count=post_row.get("like_count", 0),
        dislike_count=post_row.get("dislike_count", 0),
        comments=comments
    )

@router.put("/posts/{post_id}/comments/{comment_id}", response_model=PostCommentResponse)
def update_post_comment(post_id: int, comment_id: int, comment_update: PostCommentUpdate, current_user=Depends(get_current_user)):
    # 댓글 존재 확인
    comment_row = supabase.table("post_comment").select("*").eq("id", comment_id).eq("post_id", post_id).single().execute().data
    if not comment_row:
        raise HTTPException(status_code=404, detail="Comment not found")
    
    # 작성자 확인
    if comment_row["user_id"] != current_user["id"]:
        raise HTTPException(status_code=403, detail="You can only update your own comments")
    
    now = datetime.utcnow().isoformat()
    
    try:
        supabase.table("post_comment").update({
            "content": comment_update.content,
            "updated_at": now
        }).eq("id", comment_id).execute()
        
        updated_comment = supabase.table("post_comment").select("*").eq("id", comment_id).single().execute().data
        
        return PostCommentResponse(
            id=updated_comment["id"],
            post_id=updated_comment["post_id"],
            user_id=updated_comment["user_id"],
            user_name=current_user["username"],
            content=updated_comment["content"],
            created_at=updated_comment["created_at"],
            updated_at=updated_comment["updated_at"]
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to update comment: {str(e)}")

@router.delete("/posts/{post_id}/comments/{comment_id}")
def delete_post_comment(post_id: int, comment_id: int, current_user=Depends(get_current_user)):
    # 댓글 존재 확인
    comment_row = supabase.table("post_comment").select("*").eq("id", comment_id).eq("post_id", post_id).single().execute().data
    if not comment_row:
        raise HTTPException(status_code=404, detail="Comment not found")
    
    # 작성자 확인
    if comment_row["user_id"] != current_user["id"]:
        raise HTTPException(status_code=403, detail="You can only delete your own comments")
    
    try:
        supabase.table("post_comment").delete().eq("id", comment_id).execute()
        return {"msg": "Comment deleted successfully"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to delete comment: {str(e)}")

@router.get("/categories")
def get_categories():
    categories = [row["category"] for row in supabase.table("post").select("category").order("category").execute().data]
    return {"categories": categories}

@router.get("/tags")
def get_tags():
    tags = [row["name"] for row in supabase.table("tag").select("name").order("name").execute().data]
    return {"tags": tags} 