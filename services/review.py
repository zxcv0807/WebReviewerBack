from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel, Field
from typing import List, Optional
from datetime import datetime
from .db import get_db
import json

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
    rating: float
    pros: str
    cons: str
    created_at: str

class CommentCreate(BaseModel):
    content: str = Field(..., description="댓글 내용")

class CommentResponse(BaseModel):
    id: int
    review_id: int
    content: str
    created_at: str

class ReviewWithCommentsResponse(BaseModel):
    id: int
    site_name: str
    url: str
    summary: str
    rating: float
    pros: str
    cons: str
    created_at: str
    comments: List[CommentResponse]

# API Endpoints
@router.post("/reviews", response_model=ReviewResponse)
def create_review(review: ReviewCreate):
    conn = get_db()
    cursor = conn.cursor()
    
    try:
        now = datetime.utcnow().isoformat()
        
        cursor.execute("""
            INSERT INTO review (site_name, url, summary, rating, pros, cons, created_at)
            VALUES (%s, %s, %s, %s, %s, %s, %s)
        """, (review.site_name, review.url, review.summary, review.rating, 
              review.pros, review.cons, now))
        review_id = cursor.fetchone()[0] if cursor.description else None
        conn.commit()
        
        # 생성된 리뷰 조회
        cursor.execute("SELECT * FROM review WHERE id = %s", (review_id,))
        review_row = cursor.fetchone()
        
        return ReviewResponse(
            id=review_row[0],
            site_name=review_row[1],
            url=review_row[2],
            summary=review_row[3],
            rating=review_row[4],
            pros=review_row[5],
            cons=review_row[6],
            created_at=review_row[7]
        )
        
    except Exception as e:
        conn.rollback()
        raise HTTPException(status_code=500, detail=f"Failed to create review: {str(e)}")
    finally:
        conn.close()

@router.get("/reviews", response_model=List[ReviewWithCommentsResponse])
def get_reviews():
    conn = get_db()
    cursor = conn.cursor()
    
    try:
        # LEFT JOIN을 사용하여 리뷰와 댓글을 한 번에 조회
        cursor.execute("""
            SELECT 
                r.id, r.site_name, r.url, r.summary, r.rating, r.pros, r.cons, r.created_at,
                rc.id as comment_id, rc.content as comment_content, rc.created_at as comment_created_at
            FROM review r
            LEFT JOIN review_comment rc ON r.id = rc.review_id
            ORDER BY r.created_at DESC, rc.created_at ASC
        """)
        
        reviews_dict = {}
        
        for row in cursor.fetchall():
            review_id = row[0]
            
            # 리뷰 정보가 아직 딕셔너리에 없으면 추가
            if review_id not in reviews_dict:
                reviews_dict[review_id] = ReviewWithCommentsResponse(
                    id=review_id,
                    site_name=row[1],
                    url=row[2],
                    summary=row[3],
                    rating=row[4],
                    pros=row[5],
                    cons=row[6],
                    created_at=row[7],
                    comments=[]
                )
            
            # 댓글이 있으면 추가
            if row[8] is not None:
                comment = CommentResponse(
                    id=row[8],
                    review_id=review_id,
                    content=row[9],
                    created_at=row[10]
                )
                reviews_dict[review_id].comments.append(comment)
        
        return list(reviews_dict.values())
        
    finally:
        conn.close()

@router.get("/reviews/{review_id}", response_model=ReviewWithCommentsResponse)
def get_review(review_id: int):
    conn = get_db()
    cursor = conn.cursor()
    
    try:
        # 리뷰 조회
        cursor.execute("SELECT * FROM review WHERE id = %s", (review_id,))
        review_row = cursor.fetchone()
        
        if not review_row:
            raise HTTPException(status_code=404, detail="Review not found")
        
        # 댓글 조회
        cursor.execute("SELECT * FROM review_comment WHERE review_id = %s ORDER BY created_at ASC", (review_id,))
        comments = []
        
        for comment_row in cursor.fetchall():
            comments.append(CommentResponse(
                id=comment_row[0],
                review_id=comment_row[1],
                content=comment_row[2],
                created_at=comment_row[3]
            ))
        
        return ReviewWithCommentsResponse(
            id=review_row[0],
            site_name=review_row[1],
            url=review_row[2],
            summary=review_row[3],
            rating=review_row[4],
            pros=review_row[5],
            cons=review_row[6],
            created_at=review_row[7],
            comments=comments
        )
        
    finally:
        conn.close()

@router.post("/reviews/{review_id}/comments", response_model=CommentResponse)
def create_comment(review_id: int, comment: CommentCreate):
    conn = get_db()
    cursor = conn.cursor()
    
    try:
        # 리뷰 존재 확인
        cursor.execute("SELECT id FROM review WHERE id = %s", (review_id,))
        if not cursor.fetchone():
            raise HTTPException(status_code=404, detail="Review not found")
        
        now = datetime.utcnow().isoformat()
        
        cursor.execute("""
            INSERT INTO review_comment (review_id, content, created_at)
            VALUES (%s, %s, %s)
        """, (review_id, comment.content, now))
        
        comment_id = cursor.fetchone()[0] if cursor.description else None
        conn.commit()
        
        # 생성된 댓글 조회
        cursor.execute("SELECT * FROM review_comment WHERE id = %s", (comment_id,))
        comment_row = cursor.fetchone()
        
        return CommentResponse(
            id=comment_row[0],
            review_id=comment_row[1],
            content=comment_row[2],
            created_at=comment_row[3]
        )
        
    except HTTPException:
        raise
    except Exception as e:
        conn.rollback()
        raise HTTPException(status_code=500, detail=f"Failed to create comment: {str(e)}")
    finally:
        conn.close()

@router.put("/reviews/{review_id}", response_model=ReviewResponse)
def update_review(review_id: int, review_update: ReviewUpdate):
    conn = get_db()
    cursor = conn.cursor()
    
    try:
        # 기존 리뷰 확인
        cursor.execute("SELECT * FROM review WHERE id = %s", (review_id,))
        existing_review = cursor.fetchone()
        
        if not existing_review:
            raise HTTPException(status_code=404, detail="Review not found")
        
        # 업데이트할 필드들
        update_fields = []
        update_values = []
        
        if review_update.site_name is not None:
            update_fields.append("site_name = %s")
            update_values.append(review_update.site_name)
        
        if review_update.url is not None:
            update_fields.append("url = %s")
            update_values.append(review_update.url)
        
        if review_update.summary is not None:
            update_fields.append("summary = %s")
            update_values.append(review_update.summary)
        
        if review_update.rating is not None:
            update_fields.append("rating = %s")
            update_values.append(review_update.rating)
        
        if review_update.pros is not None:
            update_fields.append("pros = %s")
            update_values.append(review_update.pros)
        
        if review_update.cons is not None:
            update_fields.append("cons = %s")
            update_values.append(review_update.cons)
        
        if update_fields:
            update_values.append(review_id)
            
            cursor.execute(
                f"UPDATE review SET {', '.join(update_fields)} WHERE id = %s",
                update_values
            )
            conn.commit()
        
        # 업데이트된 리뷰 조회
        cursor.execute("SELECT * FROM review WHERE id = %s", (review_id,))
        review_row = cursor.fetchone()
        
        return ReviewResponse(
            id=review_row[0],
            site_name=review_row[1],
            url=review_row[2],
            summary=review_row[3],
            rating=review_row[4],
            pros=review_row[5],
            cons=review_row[6],
            created_at=review_row[7]
        )
        
    except HTTPException:
        raise
    except Exception as e:
        conn.rollback()
        raise HTTPException(status_code=500, detail=f"Failed to update review: {str(e)}")
    finally:
        conn.close()

@router.delete("/reviews/{review_id}")
def delete_review(review_id: int):
    conn = get_db()
    cursor = conn.cursor()
    
    try:
        # 리뷰 존재 확인
        cursor.execute("SELECT id FROM review WHERE id = %s", (review_id,))
        if not cursor.fetchone():
            raise HTTPException(status_code=404, detail="Review not found")
        
        # 댓글 먼저 삭제
        cursor.execute("DELETE FROM review_comment WHERE review_id = %s", (review_id,))
        
        # 리뷰 삭제
        cursor.execute("DELETE FROM review WHERE id = %s", (review_id,))
        conn.commit()
        
        return {"msg": "Review deleted successfully"}
        
    except HTTPException:
        raise
    except Exception as e:
        conn.rollback()
        raise HTTPException(status_code=500, detail=f"Failed to delete review: {str(e)}")
    finally:
        conn.close() 