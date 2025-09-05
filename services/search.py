from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel
from typing import List, Dict, Any, Optional
from datetime import datetime
from .db import supabase
import json

router = APIRouter()

# Search Response Models
class SearchResultItem(BaseModel):
    id: int
    content_type: str  # 'post', 'review', 'phishing'
    title: str
    summary: str
    url: Optional[str] = None
    created_at: str
    user_name: str = "알수없음"
    rating: Optional[float] = None  # 리뷰의 경우만
    category: Optional[str] = None  # 게시판의 경우만
    tags: Optional[List[str]] = None  # 게시판의 경우만

class SearchResponse(BaseModel):
    results: List[SearchResultItem]
    total_count: int
    current_page: int
    total_pages: int
    has_next: bool
    has_previous: bool

async def unified_search_all_content(query: str, page: int = 1, limit: int = 10, sort_by: str = "created_at") -> SearchResponse:
    """
    통합 검색: 제목, 내용, 작성자, 태그에서 키워드 검색
    자유게시판, 리뷰, 피싱 신고 모든 게시물을 검색하여 통합된 결과 반환
    """
    try:
        all_results = []
        search_keyword = f"%{query.strip()}%"
        
        # 1. 자유게시판 검색 (제목, 내용, 작성자명, 태그)
        await search_posts_content(search_keyword, all_results)
        
        # 2. 리뷰 검색 (사이트명, 요약, 장점, 단점, 작성자명)
        await search_reviews_content(search_keyword, all_results)
        
        # 3. 피싱 신고 검색 (URL, 사유, 설명, 작성자명)
        await search_phishing_content(search_keyword, all_results)
        
        # 결과 정렬
        if sort_by == "created_at":
            all_results.sort(key=lambda x: x.get("created_at", ""), reverse=True)
        
        # 페이지네이션 계산
        total_count = len(all_results)
        total_pages = (total_count + limit - 1) // limit
        offset = (page - 1) * limit
        paginated_results = all_results[offset:offset + limit]
        
        # 응답 데이터 구성
        search_results = []
        for item in paginated_results:
            search_results.append(SearchResultItem(
                id=item["id"],
                content_type=item["content_type"],
                title=item["title"],
                summary=item["summary"],
                url=item.get("url"),
                created_at=item["created_at"],
                user_name=item.get("user_name", "알수없음"),
                rating=item.get("rating"),
                category=item.get("category"),
                tags=item.get("tags", [])
            ))
        
        return SearchResponse(
            results=search_results,
            total_count=total_count,
            current_page=page,
            total_pages=total_pages,
            has_next=page < total_pages,
            has_previous=page > 1
        )
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"검색 오류: {str(e)}")

async def search_posts_content(search_keyword: str, all_results: List[Dict]):
    """자유게시판 검색"""
    try:
        # 제목, 내용, 작성자명에서 검색
        posts_response = supabase.table("post").select(
            "id, title, content, category, created_at, user_name, view_count, like_count, dislike_count"
        ).or_(
            f"title.ilike.{search_keyword},content.ilike.{search_keyword},user_name.ilike.{search_keyword}"
        ).execute()
        
        # 태그에서 검색
        tags_response = supabase.table("tag").select("post_id, name").ilike("name", search_keyword).execute()
        tag_post_ids = [tag["post_id"] for tag in tags_response.data]
        
        # 태그로 검색된 게시물들 가져오기
        tag_posts_response = []
        if tag_post_ids:
            tag_posts_response = supabase.table("post").select(
                "id, title, content, category, created_at, user_name, view_count, like_count, dislike_count"
            ).in_("id", tag_post_ids).execute()
        
        # 결과 합치기 (중복 제거)
        combined_posts = {}
        
        # 직접 검색 결과 추가
        for post in posts_response.data:
            combined_posts[post["id"]] = post
            
        # 태그 검색 결과 추가
        if tag_posts_response:
            for post in tag_posts_response.data:
                combined_posts[post["id"]] = post
        
        # 각 게시물의 태그 정보 추가
        for post_id, post in combined_posts.items():
            tag_response = supabase.table("tag").select("name").eq("post_id", post_id).execute()
            post_tags = [tag["name"] for tag in tag_response.data]
            
            # 내용 처리
            content_text = ""
            if isinstance(post.get("content"), dict):
                content_text = json.dumps(post["content"], ensure_ascii=False)
            elif isinstance(post.get("content"), str):
                content_text = post["content"]
            
            summary = content_text[:200] + "..." if len(content_text) > 200 else content_text
            
            all_results.append({
                "id": post["id"],
                "content_type": "post",
                "title": post["title"],
                "summary": summary,
                "created_at": post["created_at"],
                "user_name": post.get("user_name", "알수없음"),
                "category": post.get("category"),
                "tags": post_tags
            })
            
    except Exception as e:
        print(f"게시판 검색 오류: {e}")

async def search_reviews_content(search_keyword: str, all_results: List[Dict]):
    """리뷰 검색"""
    try:
        # 사이트명, 요약, 장점, 단점에서 검색
        reviews_response = supabase.table("review").select(
            "id, site_name, url, summary, rating, pros, cons, created_at, view_count, like_count, dislike_count, user_id"
        ).or_(
            f"site_name.ilike.{search_keyword},summary.ilike.{search_keyword},pros.ilike.{search_keyword},cons.ilike.{search_keyword}"
        ).execute()
        
        # 작성자명으로 검색
        users_response = supabase.table("user").select("id, username").ilike("username", search_keyword).execute()
        user_ids = [user["id"] for user in users_response.data]
        
        user_reviews_response = []
        if user_ids:
            user_reviews_response = supabase.table("review").select(
                "id, site_name, url, summary, rating, pros, cons, created_at, view_count, like_count, dislike_count, user_id"
            ).in_("user_id", user_ids).execute()
        
        # 결과 합치기 (중복 제거)
        combined_reviews = {}
        
        # 직접 검색 결과 추가
        for review in reviews_response.data:
            combined_reviews[review["id"]] = review
            
        # 작성자 검색 결과 추가
        if user_reviews_response:
            for review in user_reviews_response.data:
                combined_reviews[review["id"]] = review
        
        # 각 리뷰에 사용자명 추가
        for review_id, review in combined_reviews.items():
            user_name = "알수없음"
            if review.get("user_id"):
                user_response = supabase.table("user").select("username").eq("id", review["user_id"]).execute()
                if user_response.data:
                    user_name = user_response.data[0]["username"]
            
            all_results.append({
                "id": review["id"],
                "content_type": "review",
                "title": review["site_name"],
                "summary": review["summary"],
                "url": review.get("url"),
                "created_at": review["created_at"],
                "user_name": user_name,
                "rating": review.get("rating")
            })
            
    except Exception as e:
        print(f"리뷰 검색 오류: {e}")

async def search_phishing_content(search_keyword: str, all_results: List[Dict]):
    """피싱 신고 검색"""
    try:
        # URL, 사유, 설명에서 검색
        phishing_response = supabase.table("phishing_site").select(
            "id, url, reason, description, status, created_at, view_count, like_count, dislike_count, user_id"
        ).or_(
            f"url.ilike.{search_keyword},reason.ilike.{search_keyword},description.ilike.{search_keyword}"
        ).execute()
        
        # 작성자명으로 검색
        users_response = supabase.table("user").select("id, username").ilike("username", search_keyword).execute()
        user_ids = [user["id"] for user in users_response.data]
        
        user_phishing_response = []
        if user_ids:
            user_phishing_response = supabase.table("phishing_site").select(
                "id, url, reason, description, status, created_at, view_count, like_count, dislike_count, user_id"
            ).in_("user_id", user_ids).execute()
        
        # 결과 합치기 (중복 제거)
        combined_phishing = {}
        
        # 직접 검색 결과 추가
        for site in phishing_response.data:
            combined_phishing[site["id"]] = site
            
        # 작성자 검색 결과 추가
        if user_phishing_response:
            for site in user_phishing_response.data:
                combined_phishing[site["id"]] = site
        
        # 각 피싱 신고에 사용자명 추가
        for site_id, site in combined_phishing.items():
            user_name = "알수없음"
            if site.get("user_id"):
                user_response = supabase.table("user").select("username").eq("id", site["user_id"]).execute()
                if user_response.data:
                    user_name = user_response.data[0]["username"]
            
            all_results.append({
                "id": site["id"],
                "content_type": "phishing",
                "title": f"피싱 신고: {site['url']}",
                "summary": site.get("description", site["reason"]),
                "url": site["url"],
                "created_at": site["created_at"],
                "user_name": user_name
            })
            
    except Exception as e:
        print(f"피싱 사이트 검색 오류: {e}")

@router.get("/", response_model=SearchResponse, summary="통합 검색")
async def search_all(
    q: str = Query(..., description="검색어"),
    page: int = Query(1, ge=1, description="페이지 번호"),
    limit: int = Query(10, ge=1, le=50, description="페이지당 결과 수"),
    sort_by: str = Query("created_at", description="정렬 기준")
):
    """
    통합 검색 API
    - 자유게시판, 리뷰, 피싱 신고를 모두 검색
    - 제목, 내용, 작성자명, 태그(게시판만)에서 검색
    - content_type으로 게시물 유형 구분 가능
    """
    if not q.strip():
        raise HTTPException(status_code=400, detail="검색어를 입력해주세요")
    
    return await unified_search_all_content(q, page, limit, sort_by)

@router.get("/suggestions", summary="검색 추천어")
async def get_search_suggestions(
    q: str = Query(..., description="검색어 일부"),
    limit: int = Query(10, description="추천어 개수")
):
    """검색어 자동완성 추천"""
    try:
        if not q.strip():
            return {"suggestions": [], "count": 0}
            
        suggestions = []
        search_keyword = f"%{q.strip()}%"
        
        # 게시판 제목에서 추천어 찾기
        post_response = supabase.table("post").select("title").ilike("title", search_keyword).limit(limit // 3).execute()
        suggestions.extend([post["title"] for post in post_response.data])
        
        # 리뷰 사이트명에서 추천어 찾기
        review_response = supabase.table("review").select("site_name").ilike("site_name", search_keyword).limit(limit // 3).execute()
        suggestions.extend([review["site_name"] for review in review_response.data])
        
        # 태그에서 추천어 찾기
        tag_response = supabase.table("tag").select("name").ilike("name", search_keyword).limit(limit // 3).execute()
        suggestions.extend([tag["name"] for tag in tag_response.data])
        
        # 중복 제거 및 제한
        unique_suggestions = list(dict.fromkeys(suggestions))[:limit]
        
        return {
            "suggestions": unique_suggestions,
            "count": len(unique_suggestions)
        }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"추천어 검색 오류: {str(e)}")