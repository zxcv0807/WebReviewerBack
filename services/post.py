from fastapi import APIRouter, HTTPException, Depends, Response
from pydantic import BaseModel
from typing import List, Optional
from datetime import datetime
from .db import get_db
import json
from .auth import get_current_user

router = APIRouter()

class PostCreate(BaseModel):
    title: str
    category: str
    content: dict  # Lexical JSON 데이터
    tags: List[str] = []
    # user_id와 user_name은 서버에서 할당하므로 입력받지 않음

class PostUpdate(BaseModel):
    title: Optional[str] = None
    category: Optional[str] = None
    content: Optional[dict] = None
    tags: Optional[List[str]] = None

class PostResponse(BaseModel):
    id: int
    title: str
    category: str
    content: dict
    tags: List[str]
    created_at: str
    updated_at: str
    user_id: int
    user_name: str  # user 테이블에서 JOIN해서 가져온 값

@router.post("/posts", response_model=PostResponse)
def create_post(post: PostCreate, current_user=Depends(get_current_user)):
    conn = get_db()
    cursor = conn.cursor()
    
    try:
        # 현재 시간
        now = datetime.utcnow().isoformat()
        
        # Post 생성
        cursor.execute(
            "INSERT INTO post (title, category, content, created_at, updated_at, user_id, user_name) VALUES (%s, %s, %s, %s, %s, %s, %s)",
            (post.title, post.category, json.dumps(post.content), now, now, current_user["id"], current_user["username"])
        )
        post_id = cursor.fetchone()[0] if cursor.description else None
        
        # Tags 생성
        for tag_name in post.tags:
            cursor.execute(
                "INSERT INTO tag (name, post_id) VALUES (%s, %s)",
                (tag_name, post_id)
            )
        
        conn.commit()
        
        # 생성된 post + 작성자 username 조회
        cursor.execute(
            "SELECT * FROM post WHERE id = %s",
            (post_id,)
        )
        post_row = cursor.fetchone()
        
        # 태그 조회
        cursor.execute(
            "SELECT name FROM tag WHERE post_id = %s",
            (post_id,)
        )
        tags = [row[0] for row in cursor.fetchall()]
        
        return PostResponse(
            id=post_row[0],
            title=post_row[1],
            category=post_row[2],
            content=json.loads(post_row[3]),
            tags=tags,
            created_at=post_row[4],
            updated_at=post_row[5],
            user_id=post_row[6],
            user_name=post_row[7]
        )
        
    except Exception as e:
        conn.rollback()
        raise HTTPException(status_code=500, detail=f"Failed to create post: {str(e)}")
    finally:
        conn.close()

@router.get("/posts", response_model=List[PostResponse])
def get_posts(category: Optional[str] = None, tag: Optional[str] = None, type: Optional[str] = None):
    conn = get_db()
    cursor = conn.cursor()
    try:
        # category 파라미터가 'free', '자유게시판' 등 여러 값일 수 있으니 모두 허용
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
            cursor.execute("""
                SELECT DISTINCT p.* FROM post p
                JOIN tag t ON p.id = t.post_id
                WHERE t.name = %s
                ORDER BY p.created_at DESC
            """, (tag,))
        elif db_category:
            cursor.execute(
                "SELECT * FROM post WHERE category = %s ORDER BY created_at DESC",
                (db_category,)
            )
        else:
            cursor.execute("SELECT * FROM post ORDER BY created_at DESC")
        posts = []
        for post_row in cursor.fetchall():
            cursor.execute(
                "SELECT name FROM tag WHERE post_id = %s",
                (post_row[0],)
            )
            tags = [row[0] for row in cursor.fetchall()]
            user_name = post_row[7]
            if not user_name:
                cursor.execute("SELECT username FROM \"user\" WHERE id = %s", (post_row[6],))
                user_row = cursor.fetchone()
                user_name = user_row[0] if user_row else "알수없음"
            posts.append(PostResponse(
                id=post_row[0],
                title=post_row[1],
                category=post_row[2],
                content=json.loads(post_row[3]),
                tags=tags,
                created_at=post_row[4],
                updated_at=post_row[5],
                user_id=post_row[6],
                user_name=user_name
            ))
        return posts
    finally:
        conn.close()

@router.get("/posts/{post_id}", response_model=PostResponse)
def get_post(post_id: int):
    conn = get_db()
    cursor = conn.cursor()
    
    try:
        cursor.execute("SELECT * FROM post WHERE id = %s", (post_id,))
        post_row = cursor.fetchone()
        
        if not post_row:
            raise HTTPException(status_code=404, detail="Post not found")
        
        # 태그 조회
        cursor.execute(
            "SELECT name FROM tag WHERE post_id = %s",
            (post_id,)
        )
        tags = [row[0] for row in cursor.fetchall()]
        
        return PostResponse(
            id=post_row[0],
            title=post_row[1],
            category=post_row[2],
            content=json.loads(post_row[3]),
            tags=tags,
            created_at=post_row[4],
            updated_at=post_row[5],
            user_id=post_row[6],
            user_name=post_row[7]
        )
        
    finally:
        conn.close()

@router.put("/posts/{post_id}", response_model=PostResponse)
def update_post(post_id: int, post_update: PostUpdate):
    conn = get_db()
    cursor = conn.cursor()
    
    try:
        # 기존 게시글 확인
        cursor.execute("SELECT * FROM post WHERE id = %s", (post_id,))
        existing_post = cursor.fetchone()
        
        if not existing_post:
            raise HTTPException(status_code=404, detail="Post not found")
        
        # 업데이트할 필드들
        update_fields = []
        update_values = []
        
        if post_update.title is not None:
            update_fields.append("title = %s")
            update_values.append(post_update.title)
        
        if post_update.category is not None:
            update_fields.append("category = %s")
            update_values.append(post_update.category)
        
        if post_update.content is not None:
            update_fields.append("content = %s")
            update_values.append(json.dumps(post_update.content))
        
        if update_fields:
            update_fields.append("updated_at = %s")
            update_values.append(datetime.utcnow().isoformat())
            update_values.append(post_id)
            
            cursor.execute(
                f"UPDATE post SET {', '.join(update_fields)} WHERE id = %s",
                update_values
            )
        
        # 태그 업데이트
        if post_update.tags is not None:
            # 기존 태그 삭제
            cursor.execute("DELETE FROM tag WHERE post_id = %s", (post_id,))
            
            # 새 태그 추가
            for tag_name in post_update.tags:
                cursor.execute(
                    "INSERT INTO tag (name, post_id) VALUES (%s, %s)",
                    (tag_name, post_id)
                )
        
        conn.commit()
        
        # 업데이트된 게시글 조회
        return get_post(post_id)
        
    except HTTPException:
        raise
    except Exception as e:
        conn.rollback()
        raise HTTPException(status_code=500, detail=f"Failed to update post: {str(e)}")
    finally:
        conn.close()

@router.delete("/posts/{post_id}")
def delete_post(post_id: int):
    conn = get_db()
    cursor = conn.cursor()
    
    try:
        # 게시글 존재 확인
        cursor.execute("SELECT id FROM post WHERE id = %s", (post_id,))
        if not cursor.fetchone():
            raise HTTPException(status_code=404, detail="Post not found")
        
        # 게시글 삭제 (태그는 CASCADE로 자동 삭제됨)
        cursor.execute("DELETE FROM post WHERE id = %s", (post_id,))
        conn.commit()
        
        return {"msg": "Post deleted successfully"}
        
    except HTTPException:
        raise
    except Exception as e:
        conn.rollback()
        raise HTTPException(status_code=500, detail=f"Failed to delete post: {str(e)}")
    finally:
        conn.close()

@router.get("/categories")
def get_categories():
    conn = get_db()
    cursor = conn.cursor()
    
    try:
        cursor.execute("SELECT DISTINCT category FROM post ORDER BY category")
        categories = [row[0] for row in cursor.fetchall()]
        return {"categories": categories}
    finally:
        conn.close()

@router.get("/tags")
def get_tags():
    conn = get_db()
    cursor = conn.cursor()
    
    try:
        cursor.execute("SELECT DISTINCT name FROM tag ORDER BY name")
        tags = [row[0] for row in cursor.fetchall()]
        return {"tags": tags}
    finally:
        conn.close() 