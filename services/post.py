from fastapi import APIRouter, HTTPException, Depends, Response
from pydantic import BaseModel
from typing import List, Optional
from datetime import datetime
from .auth import get_current_user
from supabase import create_client, Client
import os
import json

SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_ANON_KEY = os.getenv("SUPABASE_ANON_KEY")
if not SUPABASE_URL or not SUPABASE_ANON_KEY:
    raise RuntimeError("SUPABASE_URL and SUPABASE_ANON_KEY must be set in .env")
supabase: Client = create_client(SUPABASE_URL, SUPABASE_ANON_KEY)

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
        "user_name": current_user["username"]
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

@router.get("/posts", response_model=List[PostResponse])
def get_posts(category: Optional[str] = None, tag: Optional[str] = None, type: Optional[str] = None):
    category_map = {
        '자유게시판': 'free',
        'free': 'free',
        'Free': 'free',
        'FREE': 'free',
    }
    db_category = None
    if category:
        db_category = category_map.get(category, category)
    if tag:
        post_rows = supabase.table("post").select("*", "tag(name)").eq("tag.name", tag).order("created_at", desc=True).execute().data
    elif db_category:
        post_rows = supabase.table("post").select("*").eq("category", db_category).order("created_at", desc=True).execute().data
    else:
        post_rows = supabase.table("post").select("*").order("created_at", desc=True).execute().data
    posts = []
    for post_row in post_rows:
        tags = [row["name"] for row in supabase.table("tag").select("name").eq("post_id", post_row["id"]).execute().data]
        user_name = post_row.get("user_name")
        if not user_name:
            user_row = supabase.table("user").select("username").eq("id", post_row["user_id"]).single().execute().data
            user_name = user_row["username"] if user_row else "알수없음"
        posts.append(PostResponse(
            id=post_row["id"],
            title=post_row["title"],
            category=post_row["category"],
            content=json.loads(post_row["content"]),
            tags=tags,
            created_at=post_row["created_at"],
            updated_at=post_row["updated_at"],
            user_id=post_row["user_id"],
            user_name=user_name
        ))
    return posts

@router.get("/posts/{post_id}", response_model=PostResponse)
def get_post(post_id: int):
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

@router.put("/posts/{post_id}", response_model=PostResponse)
def update_post(post_id: int, post_update: PostUpdate):
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
def delete_post(post_id: int):
    supabase.table("post").delete().eq("id", post_id).execute()
    return {"msg": "Post deleted successfully"}

@router.get("/categories")
def get_categories():
    categories = [row["category"] for row in supabase.table("post").select("category").order("category").execute().data]
    return {"categories": categories}

@router.get("/tags")
def get_tags():
    tags = [row["name"] for row in supabase.table("tag").select("name").order("name").execute().data]
    return {"tags": tags} 