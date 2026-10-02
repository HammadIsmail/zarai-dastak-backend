"""
Providers Explorer REST API
Returns public business/service information for all verified providers.
Sensitive fields (CNIC, phone, email, license, exact address) are never exposed.
"""

from fastapi import APIRouter, HTTPException, status
from app.core.database.neo4j_driver import neo4j_driver
from neo4j.time import DateTime as Neo4jDateTime

router = APIRouter()


def _serialize(value):
    """Convert Neo4j DateTime to ISO string."""
    if isinstance(value, Neo4jDateTime):
        return value.to_native().isoformat()
    return value


def _safe_provider(record) -> dict:
    """Extract public-safe provider fields from a Neo4j record."""
    p = record.get("p")
    if not p:
        return {}
    raw = dict(p)
    # Prefer live-computed values from the query over stale node properties
    computed_rating = record.get("avgRating")
    computed_reviews = record.get("totalReviews", 0)
    return {
        "id": raw.get("id"),
        "name": raw.get("name"),
        "profileImageUrl": raw.get("profileImageUrl"),
        "rating": float(computed_rating) if computed_rating is not None else float(raw.get("rating") or 0.0),
        "totalReviews": int(computed_reviews) if computed_reviews else 0,
        "completedBookings": record.get("completedBookings", 0),
        "city": raw.get("city") or raw.get("area"),
        "experience": raw.get("experience"),
        "isOnline": raw.get("isOnline", False),
        "services": [],
    }


@router.get("")
async def explore_providers(requester_id: str = "", limit: int = 50, offset: int = 0):
    """
    Return all verified, active providers with their public services.
    Excludes the requesting provider (pass requester_id to filter self).
    Sensitive data is never included.
    """
    try:
        query = """
        MATCH (p)
        WHERE (p:Provider OR p:User)
          AND p.role = 'provider'
          AND coalesce(p.isVerified, false) = true
          AND coalesce(p.isActive, true) = true
          AND ($requesterId = '' OR p.id <> $requesterId)

        // Aggregate completed bookings
        OPTIONAL MATCH (b:Booking {providerId: p.id, status: 'completed'})
        WITH p, count(b) AS completedBookings

        // Aggregate provider reviews — seekers leave reviews ABOUT providers
        // using the [:ABOUT] relationship with reviewerType = 'seeker'
        OPTIONAL MATCH (fb:Feedback {reviewerType: 'seeker'})-[:ABOUT]->(p)
        WITH p, completedBookings,
             count(fb) AS totalReviews,
             CASE WHEN count(fb) > 0 THEN avg(fb.rating) ELSE 0.0 END AS avgRating

        ORDER BY avgRating DESC, completedBookings DESC
        SKIP $offset LIMIT $limit

        // Services for each provider (active only)
        OPTIONAL MATCH (p)-[:OFFERS]->(svc:Service {isActive: true})
        OPTIONAL MATCH (v:Vehicle {id: svc.vehicleId})

        // Pre-aggregate service feedback BEFORE collect()
        OPTIONAL MATCH (svc)<-[:FOR_SERVICE]-(sfb:Feedback)
        WITH p, completedBookings, totalReviews, avgRating, svc, v,
             avg(sfb.rating) AS svcRating, count(sfb) AS svcReviewCount

        WITH p, completedBookings, totalReviews, avgRating,
             collect(
               CASE WHEN svc.id IS NOT NULL
                 THEN {
                   id: svc.id,
                   name: svc.name,
                   description: svc.description,
                   category: svc.category,
                   basePrice: svc.basePrice,
                   pricePerKm: svc.pricePerKm,
                   pricePerHour: svc.pricePerHour,
                   imageUrl: svc.imageUrl,
                   vehicleType: v.vehicleType,
                   vehicleNumber: v.vehicleNumber,
                   vehicleImageBase64: v.vehicleImageBase64,
                   serviceRating: svcRating,
                   serviceReviewCount: svcReviewCount,
                   minLoad: svc.minLoad,
                   maxLoad: svc.maxLoad,
                   loadUnit: svc.loadUnit,
                   operatingHours: svc.operatingHours,
                   features: svc.features,
                   availability: svc.availability
                 }
                 ELSE null
               END
             ) AS rawServices

        RETURN p, completedBookings, totalReviews, avgRating, rawServices
        ORDER BY avgRating DESC, completedBookings DESC
        """

        rows = neo4j_driver.execute_read(
            query,
            {"requesterId": requester_id, "limit": limit, "offset": offset},
        )

        providers = []
        if rows:
            for record in rows:
                prov = _safe_provider(record)
                if not prov.get("id"):
                    continue

                raw_services = record.get("rawServices") or []
                services = []
                for s in raw_services:
                    if not s or not s.get("id"):
                        continue
                    services.append({
                        "id": s.get("id"),
                        "name": s.get("name"),
                        "description": s.get("description"),
                        "category": s.get("category"),
                        "basePrice": s.get("basePrice", 0.0),
                        "pricePerKm": s.get("pricePerKm", 0.0),
                        "pricePerHour": s.get("pricePerHour", 0.0),
                        "imageUrl": s.get("imageUrl"),
                        "vehicleType": s.get("vehicleType"),
                        "vehicleNumber": s.get("vehicleNumber"),
                        "vehicleImageBase64": s.get("vehicleImageBase64"),
                        "serviceRating": s.get("serviceRating") or 0.0,
                        "serviceReviewCount": s.get("serviceReviewCount") or 0,
                        "minLoad": s.get("minLoad"),
                        "maxLoad": s.get("maxLoad"),
                        "loadUnit": s.get("loadUnit"),
                        "operatingHours": s.get("operatingHours"),
                        "features": s.get("features") or [],
                        "availability": s.get("availability"),
                    })

                prov["services"] = services
                providers.append(prov)

        return {
            "success": True,
            "providers": providers,
            "total": len(providers),
        }

    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to fetch providers: {str(e)}",
        )
