from fastapi import APIRouter, HTTPException, Query, Depends
from pydantic import BaseModel, Field
from typing import List, Optional, Dict, Any, Union
from datetime import datetime
from .db import supabase
from .auth import get_current_user
from .pagination import PaginationParams, PaginatedResponse, create_pagination_info, get_offset
import json

router = APIRouter()

# Search Models
class SearchParams(BaseModel):
    query: str = Field(..., description="검색어")
    content_type: Optional[str] = Field(None, description="컨텐츠 타입 필터: 'posts', 'reviews', 'phishing' 또는 전체검색시 None")
    sort_by: Optional[str] = Field("created_at", description="정렬 기준: 'created_at', 'view_count'")
    sort_order: Optional[str] = Field("desc", description="정렬 순서 (항상 desc)")
    min_rating: Optional[float] = Field(None, description="최소 평점 (리뷰 검색시)")
    max_rating: Optional[float] = Field(None, description="최대 평점 (리뷰 검색시)")
    category: Optional[str] = Field(None, description="게시판 카테고리 필터")
    tags: Optional[List[str]] = Field(None, description="태그 필터 (게시판)")

class SearchResultItem(BaseModel):
    id: int
    content_type: str  # 'post', 'review', 'phishing'
    title: str
    summary: str  # 검색 결과 요약
    url: Optional[str] = None
    created_at: str
    updated_at: Optional[str] = None
    view_count: int = 0
    like_count: int = 0
    dislike_count: int = 0
    user_name: str = "알수없음"
    rating: Optional[float] = None  # 리뷰의 경우
    category: Optional[str] = None  # 게시판의 경우
    tags: Optional[List[str]] = None  # 게시판의 경우

class SearchResponse(BaseModel):
    results: List[SearchResultItem]
    total_count: int
    summary: Dict[str, int]  # 각 컨텐츠 타입별 결과 수
    pagination: Dict[str, Any]

# Search Functions
async def search_posts(query: str, category: Optional[str] = None, tags: Optional[List[str]] = None, 
                      sort_by: str = "created_at", sort_order: str = "desc", 
                      limit: int = 20, offset: int = 0) -> Dict[str, Any]:
    """게시판 검색"""
    try:
        # 기본 쿼리 구성
        query_builder = supabase.table("post").select(
            "id, title, content, category, created_at, updated_at, user_name, view_count, like_count, dislike_count"
        )
        
        # 텍스트 검색 (제목, 사용자명에서)
        if query.strip():
            # PostgreSQL의 ilike를 사용한 대소문자 무시 검색
            query_builder = query_builder.or_(f"title.ilike.%{query}%,user_name.ilike.%{query}%")
        
        # 카테고리 필터
        if category:
            query_builder = query_builder.eq("category", category)
            
        # 정렬
        if sort_by in ["created_at", "view_count"]:
            query_builder = query_builder.order(sort_by, desc=True)
        
        # 페이지네이션
        query_builder = query_builder.range(offset, offset + limit - 1)
        
        response = query_builder.execute()
        
        # 태그 검색이 필요한 경우
        filtered_posts = []
        if tags and response.data:
            # 각 게시물의 태그 정보를 가져와서 필터링
            for post in response.data:
                tag_response = supabase.table("tag").select("name").eq("post_id", post["id"]).execute()
                post_tags = [tag["name"] for tag in tag_response.data]
                
                # 요청된 태그 중 하나라도 포함되면 결과에 추가
                if any(tag in post_tags for tag in tags):
                    post["tags"] = post_tags
                    filtered_posts.append(post)
            posts_data = filtered_posts
        else:
            # 태그 필터가 없으면 모든 결과의 태그 정보를 추가
            posts_data = []
            for post in response.data:
                tag_response = supabase.table("tag").select("name").eq("post_id", post["id"]).execute()
                post["tags"] = [tag["name"] for tag in tag_response.data]
                posts_data.append(post)
        
        return {
            "data": posts_data,
            "count": len(posts_data)
        }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"게시판 검색 오류: {str(e)}")

async def search_reviews(query: str, min_rating: Optional[float] = None, max_rating: Optional[float] = None,
                        sort_by: str = "created_at", sort_order: str = "desc",
                        limit: int = 20, offset: int = 0) -> Dict[str, Any]:
    """리뷰 검색"""
    try:
        query_builder = supabase.table("review").select(
            "id, site_name, url, summary, rating, pros, cons, created_at, updated_at, view_count, like_count, dislike_count, user_id"
        )
        
        # 텍스트 검색 (사이트명, 요약, 장점, 단점에서)
        if query.strip():
            query_builder = query_builder.or_(
                f"site_name.ilike.%{query}%,summary.ilike.%{query}%,pros.ilike.%{query}%,cons.ilike.%{query}%"
            )
        
        # 평점 필터
        if min_rating is not None:
            query_builder = query_builder.gte("rating", min_rating)
        if max_rating is not None:
            query_builder = query_builder.lte("rating", max_rating)
            
        # 정렬
        valid_sorts = ["created_at", "view_count"]
        if sort_by in valid_sorts:
            query_builder = query_builder.order(sort_by, desc=True)
        
        # 페이지네이션
        query_builder = query_builder.range(offset, offset + limit - 1)
        
        response = query_builder.execute()
        
        # 사용자 이름 추가
        for review in response.data:
            if review.get("user_id"):
                user_response = supabase.table("user").select("username").eq("id", review["user_id"]).execute()
                review["user_name"] = user_response.data[0]["username"] if user_response.data else "알수없음"
            else:
                review["user_name"] = "알수없음"
        
        return {
            "data": response.data,
            "count": len(response.data)
        }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"리뷰 검색 오류: {str(e)}")

async def search_phishing_sites(query: str, sort_by: str = "created_at", sort_order: str = "desc",
                               limit: int = 20, offset: int = 0) -> Dict[str, Any]:
    """피싱 사이트 검색"""
    try:
        query_builder = supabase.table("phishing_site").select(
            "id, url, reason, description, status, created_at, updated_at, view_count, like_count, dislike_count, user_id"
        )
        
        # 텍스트 검색 (URL, 사유, 설명에서)
        if query.strip():
            query_builder = query_builder.or_(
                f"url.ilike.%{query}%,reason.ilike.%{query}%,description.ilike.%{query}%"
            )
        
        # 정렬
        if sort_by in ["created_at", "view_count"]:
            query_builder = query_builder.order(sort_by, desc=True)
        
        # 페이지네이션
        query_builder = query_builder.range(offset, offset + limit - 1)
        
        response = query_builder.execute()
        
        # 사용자 이름 추가
        for site in response.data:
            if site.get("user_id"):
                user_response = supabase.table("user").select("username").eq("id", site["user_id"]).execute()
                site["user_name"] = user_response.data[0]["username"] if user_response.data else "알수없음"
            else:
                site["user_name"] = "알수없음"
        
        return {
            "data": response.data,
            "count": len(response.data)
        }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"피싱 사이트 검색 오류: {str(e)}")

def format_search_results(posts_data: List[Dict], reviews_data: List[Dict], 
                         phishing_data: List[Dict]) -> List[SearchResultItem]:
    """검색 결과를 통일된 형식으로 변환"""
    results = []
    
    # 게시판 결과 처리
    for post in posts_data:
        # content가 dict 형태이면 텍스트로 변환
        content_text = ""
        if isinstance(post.get("content"), dict):
            content_text = json.dumps(post["content"], ensure_ascii=False)
        elif isinstance(post.get("content"), str):
            content_text = post["content"]
            
        results.append(SearchResultItem(
            id=post["id"],
            content_type="post",
            title=post["title"],
            summary=content_text[:200] + "..." if len(content_text) > 200 else content_text,
            created_at=post["created_at"],
            updated_at=post.get("updated_at"),
            view_count=post.get("view_count", 0),
            like_count=post.get("like_count", 0),
            dislike_count=post.get("dislike_count", 0),
            user_name=post.get("user_name", "알수없음"),
            category=post.get("category"),
            tags=post.get("tags", [])
        ))
    
    # 리뷰 결과 처리
    for review in reviews_data:
        results.append(SearchResultItem(
            id=review["id"],
            content_type="review",
            title=review["site_name"],
            summary=review["summary"],
            url=review.get("url"),
            created_at=review["created_at"],
            updated_at=review.get("updated_at"),
            view_count=review.get("view_count", 0),
            like_count=review.get("like_count", 0),
            dislike_count=review.get("dislike_count", 0),
            user_name=review.get("user_name", "알수없음"),
            rating=review.get("rating")
        ))
    
    # 피싱 사이트 결과 처리
    for site in phishing_data:
        results.append(SearchResultItem(
            id=site["id"],
            content_type="phishing",
            title=f"피싱 신고: {site['url']}",
            summary=site.get("description", site["reason"]),
            url=site["url"],
            created_at=site["created_at"],
            updated_at=site.get("updated_at"),
            view_count=site.get("view_count", 0),
            like_count=site.get("like_count", 0),
            dislike_count=site.get("dislike_count", 0),
            user_name=site.get("user_name", "알수없음")
        ))
    
    return results

@router.get("/", response_model=SearchResponse, summary="통합 검색")
async def unified_search(
    q: str = Query(..., description="검색어"),
    content_type: Optional[str] = Query(None, description="컨텐츠 타입: 'posts', 'reviews', 'phishing'"),
    sort_by: str = Query("created_at", description="정렬 기준: created_at, view_count"),
    sort_order: str = Query("desc", description="정렬 순서 (항상 desc)"),
    min_rating: Optional[float] = Query(None, description="최소 평점 (리뷰)"),
    max_rating: Optional[float] = Query(None, description="최대 평점 (리뷰)"),
    category: Optional[str] = Query(None, description="게시판 카테고리"),
    tags: Optional[str] = Query(None, description="태그 (콤마로 구분)"),
    pagination: PaginationParams = Depends()
):
    """
    통합 검색 API
    - 게시판, 리뷰, 피싱 사이트를 통합 검색
    - 카테고리별 필터링 가능
    - 다양한 정렬 옵션 제공
    """
    try:
        # 태그 파라미터 파싱
        tag_list = None
        if tags:
            tag_list = [tag.strip() for tag in tags.split(",") if tag.strip()]
        
        # 페이지네이션 계산
        offset = get_offset(pagination.page, pagination.page_size)
        per_type_limit = pagination.page_size if content_type else pagination.page_size // 3
        
        posts_data = []
        reviews_data = []
        phishing_data = []
        
        # 컨텐츠 타입별 검색
        if content_type == "posts" or not content_type:
            posts_result = await search_posts(
                q, category, tag_list, sort_by, sort_order, 
                per_type_limit, offset if content_type == "posts" else 0
            )
            posts_data = posts_result["data"]
        
        if content_type == "reviews" or not content_type:
            reviews_result = await search_reviews(
                q, min_rating, max_rating, sort_by, sort_order,
                per_type_limit, offset if content_type == "reviews" else 0
            )
            reviews_data = reviews_result["data"]
        
        if content_type == "phishing" or not content_type:
            phishing_result = await search_phishing_sites(
                q, sort_by, sort_order,
                per_type_limit, offset if content_type == "phishing" else 0
            )
            phishing_data = phishing_result["data"]
        
        # 결과 통합 및 포맷팅
        all_results = format_search_results(posts_data, reviews_data, phishing_data)
        
        # 통합 검색시 날짜 기준으로 재정렬
        if not content_type:
            if sort_by == "view_count":
                all_results.sort(key=lambda x: x.view_count, reverse=True)
            else:
                all_results.sort(key=lambda x: x.created_at, reverse=True)
            # 페이지네이션 적용
            total_count = len(all_results)
            all_results = all_results[offset:offset + pagination.page_size]
        else:
            total_count = len(all_results)
        
        # 요약 정보
        summary = {
            "posts": len(posts_data),
            "reviews": len(reviews_data),
            "phishing": len(phishing_data)
        }
        
        # 페이지네이션 정보
        pagination_info = create_pagination_info(
            pagination.page,
            pagination.page_size,
            total_count
        )
        
        return SearchResponse(
            results=all_results,
            total_count=total_count,
            summary=summary,
            pagination=pagination_info
        )
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"검색 오류: {str(e)}")

@router.get("/suggestions", summary="검색 추천어")
async def get_search_suggestions(
    q: str = Query(..., description="검색어 일부"),
    limit: int = Query(10, description="추천어 개수")
):
    """
    검색어 자동완성 추천
    """
    try:
        suggestions = []
        
        # 게시판 제목에서 추천어 찾기
        post_response = supabase.table("post").select("title").ilike("title", f"%{q}%").limit(limit // 3).execute()
        suggestions.extend([post["title"] for post in post_response.data])
        
        # 리뷰 사이트명에서 추천어 찾기
        review_response = supabase.table("review").select("site_name").ilike("site_name", f"%{q}%").limit(limit // 3).execute()
        suggestions.extend([review["site_name"] for review in review_response.data])
        
        # 태그에서 추천어 찾기
        tag_response = supabase.table("tag").select("name").ilike("name", f"%{q}%").limit(limit // 3).execute()
        suggestions.extend([tag["name"] for tag in tag_response.data])
        
        # 중복 제거 및 제한
        unique_suggestions = list(dict.fromkeys(suggestions))[:limit]
        
        return {
            "suggestions": unique_suggestions,
            "count": len(unique_suggestions)
        }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"추천어 검색 오류: {str(e)}")