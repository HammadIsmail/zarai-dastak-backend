"""
Recommendation model — scored service suggestions for seekers.

Scoring weights:
  3.0  — service category matches seeker's explicit interest
  2.0  — service category matches a category the seeker has previously booked
  0.0–1.0  — provider rating bonus (rating / 5.0)
  0.0–0.5  — recency bonus (newer services score higher, max 0.5)

Results are de-duplicated, capped at 15, and sorted by descending total score.
"""

from typing import List, Dict, Any, Optional
from math import radians, sin, cos, sqrt, atan2
from app.core.database.neo4j_driver import neo4j_driver


def _haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    R = 6371.0
    dlat = radians(lat2 - lat1)
    dlon = radians(lon2 - lon1)
    a = sin(dlat / 2) ** 2 + cos(radians(lat1)) * cos(radians(lat2)) * sin(dlon / 2) ** 2
    return R * 2 * atan2(sqrt(a), sqrt(1 - a))


class Recommendation:

    @staticmethod
    def get_for_seeker(
        seeker_id: str,
        limit: int = 15,
        latitude: Optional[float] = None,
        longitude: Optional[float] = None,
    ) -> List[Dict[str, Any]]:
        """
        Return scored, de-duplicated service recommendations for a seeker.
        Combines interest-match, booking-history match, provider quality, and recency.
        """
        query = """
        // ── 1. Seeker context ─────────────────────────────────────────────────
        // Match by id regardless of label (User, Seeker, or Provider node)
        OPTIONAL MATCH (s)
        WHERE (s:Seeker OR s:User OR s:Provider) AND s.id = $seekerId
        WITH coalesce(s.interests, []) AS interests

        // Pull booked service categories from completed bookings
        OPTIONAL MATCH (b:Booking {seekerId: $seekerId, status: 'completed'})
        WITH interests,
             collect(DISTINCT b.serviceType)[..20] AS bookedCategories

        // ── 2. Active services from verified providers only ───────────────────
        MATCH (svc:Service {isActive: true})
        MATCH (prov)
        WHERE (prov:Provider OR prov:User) AND prov.id = svc.providerId
          AND coalesce(prov.isVerified, false) = true
          AND prov.id <> $seekerId

        // ── 3. Scoring ────────────────────────────────────────────────────────
        WITH svc, prov, interests, bookedCategories,

             CASE WHEN svc.category IN interests THEN 3.0 ELSE 0.0 END
               AS interestScore,

             CASE WHEN svc.category IN bookedCategories THEN 2.0 ELSE 0.0 END
               AS historyScore,

             coalesce(prov.rating, 0.0) / 5.0 AS qualityScore,

             CASE
               WHEN svc.createdAt IS NOT NULL AND duration.between(svc.createdAt, datetime()).days <= 7  THEN 0.5
               WHEN svc.createdAt IS NOT NULL AND duration.between(svc.createdAt, datetime()).days <= 30 THEN 0.25
               ELSE 0.0
             END AS recencyScore,

             size(interests)       AS prefCount,
             size(bookedCategories) AS histCount

        // ── 4. Filter ─────────────────────────────────────────────────────────
        // When the seeker has interests OR booking history → only return services
        // that match at least one preference or previously-booked category.
        // Cold-start (no preferences, no history) → return all services so the
        // feed is never empty.
        WHERE (prefCount = 0 AND histCount = 0)
           OR (interestScore + historyScore > 0)

        WITH svc, prov,
             round((interestScore + historyScore + qualityScore + recencyScore) * 100) / 100.0
               AS totalScore

        ORDER BY totalScore DESC, svc.createdAt DESC
        LIMIT $limit

        // ── 5. Enrich with vehicle context ───────────────────────────────────
        OPTIONAL MATCH (v:Vehicle {id: svc.vehicleId})
        RETURN
            svc,
            totalScore,
            prov.name                  AS providerName,
            coalesce(prov.rating, 0.0) AS providerRating,
            prov.profileImageUrl       AS providerImageUrl,
            v.vehicleType              AS vehicleType,
            v.vehicleNumber            AS vehicleNumber,
            v.vehicleImageBase64       AS vehicleImageBase64,
            COALESCE(svc.serviceBaseLatitude, prov.latitude)   AS svcLat,
            COALESCE(svc.serviceBaseLongitude, prov.longitude) AS svcLon
        ORDER BY totalScore DESC
        """

        # Fetch a larger pool when location-boosting so nearby services can
        # bubble past lower-scored but interest-matched ones.
        fetch_limit = limit * 3 if (latitude is not None and longitude is not None) else limit

        result = neo4j_driver.execute_read(
            query, {'seekerId': seeker_id, 'limit': fetch_limit}
        )

        recommendations = []
        if result:
            for record in result:
                svc_node = record.get('svc')
                if not svc_node:
                    continue
                svc = Recommendation._serialize(dict(svc_node))
                base_score = record.get('totalScore', 0.0) or 0.0
                svc['recommendationScore'] = base_score
                svc['providerName']       = record.get('providerName')
                svc['providerRating']     = record.get('providerRating')
                svc['providerImageUrl']   = record.get('providerImageUrl')
                svc['vehicleType']        = record.get('vehicleType')
                svc['vehicleNumber']      = record.get('vehicleNumber')
                svc['vehicleImageBase64'] = record.get('vehicleImageBase64')
                svc['distanceKm']         = None

                # Proximity boost: add up to +1.0 for services within 100 km
                if latitude is not None and longitude is not None:
                    svc_lat = record.get('svcLat')
                    svc_lon = record.get('svcLon')
                    if svc_lat is not None and svc_lon is not None:
                        try:
                            dist_km = _haversine_km(
                                latitude, longitude, float(svc_lat), float(svc_lon)
                            )
                            svc['distanceKm'] = round(dist_km, 1)
                            proximity_score = max(0.0, 1.0 - dist_km / 100.0)
                            svc['recommendationScore'] = round(base_score + proximity_score, 2)
                        except Exception:
                            pass

                recommendations.append(svc)

        # Re-sort after proximity boost and trim to requested limit
        if latitude is not None and longitude is not None:
            recommendations.sort(
                key=lambda r: r.get('recommendationScore', 0.0), reverse=True
            )
        return recommendations[:limit]

    @staticmethod
    def get_by_category(category: str, limit: int = 10) -> List[Dict[str, Any]]:
        """Return active services for a specific category (used for notification deep-link)."""
        query = """
        MATCH (svc:Service {isActive: true, category: $category})
        OPTIONAL MATCH (prov)
        WHERE (prov:Provider OR prov:Seeker OR prov:User) AND prov.id = svc.providerId
          AND coalesce(prov.isVerified, false) = true
        OPTIONAL MATCH (v:Vehicle {id: svc.vehicleId})
        RETURN svc,
               prov.name            AS providerName,
               coalesce(prov.rating, 0.0) AS providerRating,
               prov.profileImageUrl AS providerImageUrl,
               v.vehicleType        AS vehicleType,
               v.vehicleImageBase64 AS vehicleImageBase64
        ORDER BY svc.createdAt DESC
        LIMIT $limit
        """
        result = neo4j_driver.execute_read(query, {'category': category, 'limit': limit})
        services = []
        if result:
            for record in result:
                svc_node = record.get('svc') or record['svc']
                if not svc_node:
                    continue
                svc = Recommendation._serialize(dict(svc_node))
                svc['providerName']       = record.get('providerName')
                svc['providerRating']     = record.get('providerRating')
                svc['providerImageUrl']   = record.get('providerImageUrl')
                svc['vehicleType']        = record.get('vehicleType')
                svc['vehicleImageBase64'] = record.get('vehicleImageBase64')
                services.append(svc)
        return services

    @staticmethod
    def _serialize(data: Dict[str, Any]) -> Dict[str, Any]:
        """Convert Neo4j datetime types to ISO strings."""
        from neo4j.time import DateTime as Neo4jDateTime
        from datetime import datetime
        out = {}
        for k, v in data.items():
            if isinstance(v, Neo4jDateTime):
                out[k] = v.to_native().isoformat()
            elif isinstance(v, datetime):
                out[k] = v.isoformat()
            else:
                out[k] = v
        return out
