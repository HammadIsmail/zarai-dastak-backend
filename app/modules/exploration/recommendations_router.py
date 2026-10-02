"""
Recommendations REST API Controller
Personalized service suggestions for seekers.
"""

from fastapi import APIRouter, HTTPException, status, Query
from typing import List, Optional
from pydantic import BaseModel
from app.modules.exploration.repository import Recommendation
from app.modules.users.repository import User

router = APIRouter()


class InterestsUpdateRequest(BaseModel):
    interests: List[str]


@router.get("/{seeker_id}")
async def get_recommendations(
    seeker_id: str,
    limit: int = 15,
    latitude: Optional[float] = Query(None, description="Seeker latitude for proximity scoring"),
    longitude: Optional[float] = Query(None, description="Seeker longitude for proximity scoring"),
):
    """Return scored, personalized service recommendations for a seeker."""
    try:
        recommendations = Recommendation.get_for_seeker(
            seeker_id,
            limit=limit,
            latitude=latitude,
            longitude=longitude,
        )
        return {
            "success": True,
            "recommendations": recommendations,
            "total": len(recommendations),
        }
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to fetch recommendations: {str(e)}",
        )


@router.get("/{seeker_id}/interests")
async def get_interests(seeker_id: str):
    """Return the seeker's stored interest list."""
    try:
        interests = User.get_interests(seeker_id)
        return {"success": True, "interests": interests}
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to fetch interests: {str(e)}",
        )


@router.put("/{seeker_id}/interests")
async def update_interests(seeker_id: str, payload: InterestsUpdateRequest):
    """Replace the seeker's interest list."""
    try:
        updated = User.update_interests(seeker_id, payload.interests)
        if not updated:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Seeker not found",
            )
        return {"success": True, "interests": payload.interests}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to update interests: {str(e)}",
        )
