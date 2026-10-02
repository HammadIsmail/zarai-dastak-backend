"""
Neo4j Database Layer for Haulistry Admin Module.
Ported from admin_dashboard/core/database.py and integrated with backend's neo4j_driver.
Includes robust serialization of Neo4j types (Date, DateTime, etc.) to JSON-safe primitives.
"""

from typing import Any, Optional
import uuid
import logging
from app.core.database.neo4j_driver import neo4j_driver
from .config import admin_settings

logger = logging.getLogger(__name__)


def serialize_neo4j(obj: Any) -> Any:
    """Recursively convert Neo4j types to JSON-serializable Python types."""
    if obj is None:
        return None
    if isinstance(obj, dict):
        return {k: serialize_neo4j(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [serialize_neo4j(v) for v in obj]
    if hasattr(obj, "isoformat"):
        return obj.isoformat()
    if type(obj).__module__.startswith("neo4j"):
        return str(obj)
    return obj


def run_query(cypher: str, params: Optional[dict] = None, write: bool = False) -> list[dict]:
    """Execute Cypher query and return a list of JSON-safe dicts."""
    params = params or {}
    try:
        with neo4j_driver.get_session() as session:
            def _tx(tx):
                res = tx.run(cypher, **params)
                return [dict(record) for record in res]

            records = session.execute_write(_tx) if write else session.execute_read(_tx)
            return serialize_neo4j(records)
    except Exception as e:
        logger.error(f"Admin run_query error: {e}", exc_info=True)
        return []


def is_connected() -> bool:
    """Check Neo4j connectivity."""
    try:
        with neo4j_driver.get_session() as s:
            r = s.run("RETURN 1 AS n").single()
            return bool(r and r["n"] == 1)
    except Exception:
        return False


# ── Platform Statistics ───────────────────────────────────────────────────────

def get_platform_stats() -> dict:
    q = """
    MATCH (p:Provider) WITH count(p) AS totalProviders
    MATCH (s:Seeker)   WITH totalProviders, count(s) AS totalSeekers
    WITH totalProviders, totalSeekers, (totalProviders + totalSeekers) AS totalUsers
    OPTIONAL MATCH (b) WHERE any(lbl IN labels(b) WHERE lbl STARTS WITH 'Booking')
    WITH totalUsers, totalProviders, totalSeekers, count(b) AS totalBookings
    OPTIONAL MATCH (cb)
    WHERE any(lbl IN labels(cb) WHERE lbl STARTS WITH 'Booking')
      AND cb.status = 'completed'
    WITH totalUsers, totalProviders, totalSeekers, totalBookings,
         count(cb) AS completedBookings
    OPTIONAL MATCH (pb:Provider)
    WHERE pb.isVerified IS NULL OR pb.isVerified = false
    WITH totalUsers, totalProviders, totalSeekers,
         totalBookings, completedBookings, count(pb) AS pendingVerifications
    RETURN totalUsers, totalProviders, totalSeekers,
           totalBookings, completedBookings, pendingVerifications
    """
    rows = run_query(q)
    return rows[0] if rows else {
        "totalUsers": 0, "totalProviders": 0, "totalSeekers": 0,
        "totalBookings": 0, "completedBookings": 0, "pendingVerifications": 0
    }


def get_revenue_stats() -> dict:
    q = """
    MATCH (b)
    WHERE any(lbl IN labels(b) WHERE lbl STARTS WITH 'Booking')
      AND b.status = 'completed'
    RETURN
      sum(COALESCE(b.finalPrice, b.estimatedPrice, 0)) AS totalRevenue,
      avg(COALESCE(b.finalPrice, b.estimatedPrice, 0)) AS avgBookingValue,
      count(b) AS completedCount
    """
    rows = run_query(q)
    return rows[0] if rows else {"totalRevenue": 0, "avgBookingValue": 0, "completedCount": 0}


def get_bookings_by_status() -> list[dict]:
    q = """
    MATCH (b) WHERE any(lbl IN labels(b) WHERE lbl STARTS WITH 'Booking')
    RETURN b.status AS status, count(b) AS count
    ORDER BY count DESC
    """
    return run_query(q)


def get_bookings_trend(days: int = 30) -> list[dict]:
    q = """
    MATCH (b)
    WHERE any(lbl IN labels(b) WHERE lbl STARTS WITH 'Booking')
      AND b.createdAt >= datetime() - duration({days: $days})
    RETURN date(b.createdAt) AS date, count(b) AS bookings
    ORDER BY date ASC
    """
    return run_query(q, {"days": days})


def get_services_by_category() -> list[dict]:
    q = """
    MATCH (s:Service {isActive: true})
    RETURN s.category AS category, count(s) AS count
    ORDER BY count DESC
    """
    return run_query(q)


def get_revenue_by_category() -> list[dict]:
    q = """
    MATCH (b)
    WHERE any(lbl IN labels(b) WHERE lbl STARTS WITH 'Booking')
      AND b.status = 'completed'
    RETURN COALESCE(b.serviceType, 'other') AS category,
           count(b) AS bookings,
           sum(COALESCE(b.finalPrice, b.estimatedPrice, 0)) AS revenue
    ORDER BY revenue DESC
    """
    return run_query(q)


def get_daily_revenue(days: int = 30) -> list[dict]:
    q = """
    MATCH (b)
    WHERE any(lbl IN labels(b) WHERE lbl STARTS WITH 'Booking')
      AND b.status = 'completed'
      AND b.updatedAt >= datetime() - duration({days: $days})
    RETURN date(b.updatedAt) AS date,
           count(b) AS bookings,
           sum(COALESCE(b.finalPrice, b.estimatedPrice, 0)) AS revenue
    ORDER BY date ASC
    """
    return run_query(q, {"days": days})


# ── Users & Providers ─────────────────────────────────────────────────────────

def get_all_users(
    role: Optional[str] = None,
    page: int = 0,
    size: int = 50,
    search: Optional[str] = None,
    status: Optional[str] = None
) -> list[dict]:
    if role == "provider":
        match_clause = "MATCH (u:Provider)"
    elif role == "seeker":
        match_clause = "MATCH (u:Seeker)"
    else:
        match_clause = "MATCH (u:Provider|Seeker)"

    where_clauses = []
    params: dict[str, Any] = {"skip": page * size, "limit": size}

    if status == "active":
        where_clauses.append("u.isActive = true")
    elif status == "inactive":
        where_clauses.append("(u.isActive = false OR u.isActive IS NULL)")
    elif status == "verified":
        where_clauses.append("u.isVerified = true")
    elif status == "unverified":
        where_clauses.append("(u.isVerified = false OR u.isVerified IS NULL)")

    if search:
        params["search"] = f"(?i).*{search}.*"
        where_clauses.append(
            "(u.name =~ $search OR u.email =~ $search OR u.phone =~ $search)"
        )

    where_str = ("WHERE " + " AND ".join(where_clauses)) if where_clauses else ""

    q = f"""
    {match_clause}
    {where_str}
    RETURN u.id AS id, u.name AS name, u.email AS email,
           u.phone AS phone, u.role AS role,
           COALESCE(u.isVerified, false) AS isVerified,
           COALESCE(u.isActive, false) AS isActive,
           COALESCE(u.rating, 0.0) AS rating,
           u.createdAt AS createdAt,
           u.profileImageUrl AS profileImageUrl,
           u.rejectionReason AS rejectionReason
    ORDER BY u.createdAt DESC
    SKIP $skip LIMIT $limit
    """
    return run_query(q, params)


def get_user_detail(user_id: str) -> dict:
    q = """
    MATCH (u {id: $id})
    WHERE u:Provider OR u:Seeker OR u:User
    OPTIONAL MATCH (u)-[:OWNS]->(v:Vehicle)
    OPTIONAL MATCH (u)-[:OFFERS]->(s:Service)
    WITH u,
         collect(DISTINCT {id: v.id, type: v.vehicleType, number: v.vehicleNumber,
                            isAvailable: v.isAvailable, isVerified: v.isVerified}) AS vehicles,
         collect(DISTINCT {id: s.id, name: s.name, category: s.category,
                            isActive: s.isActive, basePrice: s.basePrice}) AS services,
         collect(v)[0] AS firstVehicle
    RETURN u.id AS id, u.name AS name, u.email AS email,
           u.phone AS phone, u.role AS role,
           COALESCE(u.isVerified, false) AS isVerified,
           COALESCE(u.isActive, false) AS isActive,
           COALESCE(u.rating, 0.0) AS rating, u.cnic AS cnic,
           u.createdAt AS createdAt, u.updatedAt AS updatedAt,
           u.profileImageUrl        AS profileImageUrl,
           u.latitude AS latitude, u.longitude AS longitude,
           u.rejectionReason        AS rejectionReason,
           u.cnicFrontImageBase64   AS cnicFrontImageBase64,
           u.cnicBackImageBase64    AS cnicBackImageBase64,
           u.licenseImageBase64     AS licenseImageBase64,
           firstVehicle.vehicleImageBase64 AS vehicleImageBase64,
           firstVehicle.vehicleImageUrl    AS vehicleImageUrl,
           vehicles, services
    """
    rows = run_query(q, {"id": user_id})
    return rows[0] if rows else {}


def get_pending_providers() -> list[dict]:
    q = """
    MATCH (p:Provider)
    WHERE p.isVerified IS NULL OR p.isVerified = false
    OPTIONAL MATCH (p)-[:OWNS]->(v:Vehicle)
    WITH p, count(v) AS vehicleCount, collect(v)[0] AS firstVehicle
    RETURN p.id AS id, p.name AS name, p.email AS email,
           p.phone AS phone, p.cnic AS cnic,
           COALESCE(p.isVerified, false) AS isVerified,
           COALESCE(p.isActive, false) AS isActive,
           p.createdAt AS createdAt,
           p.profileImageUrl AS profileImageUrl,
           p.rejectionReason AS rejectionReason,
           p.cnicFrontImageBase64 AS cnicFrontImageBase64,
           p.cnicBackImageBase64  AS cnicBackImageBase64,
           p.licenseImageBase64   AS licenseImageBase64,
           firstVehicle.vehicleImageBase64 AS vehicleImageBase64,
           firstVehicle.vehicleImageUrl    AS vehicleImageUrl,
           vehicleCount
    ORDER BY p.createdAt DESC
    """
    return run_query(q)


def verify_provider(provider_id: str) -> bool:
    q = """
    MATCH (p {id: $id}) WHERE p:Provider OR p:User
    SET p.isVerified      = true,
        p.isActive        = true,
        p.rejectionReason = null,
        p.verifiedAt      = datetime(),
        p.updatedAt       = datetime()
    WITH p
    OPTIONAL MATCH (p)-[:OWNS]->(v:Vehicle)
    SET v.isAvailable = true,
        v.isVerified  = true,
        v.updatedAt   = datetime()
    RETURN p.id AS id
    """
    rows = run_query(q, {"id": provider_id}, write=True)
    return bool(rows)


def reject_provider(provider_id: str, reason: str) -> bool:
    q = """
    MATCH (p {id: $id}) WHERE p:Provider OR p:User
    SET p.isVerified = false,
        p.isActive   = false,
        p.rejectionReason = $reason,
        p.updatedAt  = datetime()
    RETURN p.id AS id
    """
    rows = run_query(q, {"id": provider_id, "reason": reason}, write=True)
    return bool(rows)


def toggle_user_status(user_id: str, active: bool) -> bool:
    q = """
    MATCH (u {id: $id})
    WHERE u:Provider OR u:Seeker OR u:User
    SET u.isActive = $active, u.updatedAt = datetime()
    RETURN u.id AS id
    """
    rows = run_query(q, {"id": user_id, "active": active}, write=True)
    return bool(rows)


def delete_user(user_id: str) -> bool:
    """Permanently delete a user and ALL related nodes/relationships (cascade)."""
    steps = [
        # 1. Services attached to the user's vehicles
        """
        MATCH (u {id: $id}) WHERE u:Provider OR u:Seeker OR u:User
        OPTIONAL MATCH (u)-[:OWNS]->(v:Vehicle)-[:PROVIDES]->(s:Service)
        DETACH DELETE s
        """,
        # 2. Services offered directly by the user
        """
        MATCH (u {id: $id}) WHERE u:Provider OR u:Seeker OR u:User
        OPTIONAL MATCH (u)-[:OFFERS]->(s:Service)
        DETACH DELETE s
        """,
        # 3. Vehicles owned by the user
        """
        MATCH (u {id: $id}) WHERE u:Provider OR u:Seeker OR u:User
        OPTIONAL MATCH (u)-[:OWNS]->(v:Vehicle)
        DETACH DELETE v
        """,
        # 4. FareOffers on bookings the user is part of
        """
        MATCH (b) WHERE any(lbl IN labels(b) WHERE lbl STARTS WITH 'Booking')
          AND (b.seekerId = $id OR b.providerId = $id)
        OPTIONAL MATCH (b)-[:HAS_OFFER]->(fo:FareOffer)
        DETACH DELETE fo
        """,
        # 5. FareOffers made directly by the user (provider path)
        """
        MATCH (u {id: $id}) WHERE u:Provider OR u:Seeker OR u:User
        OPTIONAL MATCH (u)-[:MADE_OFFER]->(fo:FareOffer)
        DETACH DELETE fo
        """,
        # 6. Bookings where user is seeker or provider
        """
        MATCH (b) WHERE any(lbl IN labels(b) WHERE lbl STARTS WITH 'Booking')
          AND (b.seekerId = $id OR b.providerId = $id)
        DETACH DELETE b
        """,
        # 7. Chat messages
        """
        MATCH (m:Message) WHERE m.senderId = $id OR m.receiverId = $id
        DETACH DELETE m
        """,
        # 8. Voice messages
        """
        MATCH (vm:VoiceMessage) WHERE vm.senderId = $id OR vm.receiverId = $id
        DETACH DELETE vm
        """,
        # 9. Calls
        """
        MATCH (c:Call) WHERE c.callerId = $id OR c.receiverId = $id
        DETACH DELETE c
        """,
        # 10. Location tracking nodes
        """
        MATCH (loc:Location {userId: $id})
        DETACH DELETE loc
        """,
        # 11. Feedback / ratings
        """
        MATCH (f:Feedback) WHERE f.providerId = $id OR f.seekerId = $id
        DETACH DELETE f
        """,
        # 12. Notifications
        """
        MATCH (n:Notification {userId: $id})
        DETACH DELETE n
        """,
        # 13. The user node itself
        """
        MATCH (u {id: $id}) WHERE u:Provider OR u:Seeker OR u:User
        DETACH DELETE u
        RETURN 1 AS deleted
        """,
    ]

    for cypher in steps:
        run_query(cypher, {"id": user_id}, write=True)

    check = run_query(
        "MATCH (u {id: $id}) WHERE u:Provider OR u:Seeker OR u:User RETURN u LIMIT 1",
        {"id": user_id},
    )
    return len(check) == 0


def get_provider_performance(provider_id: str) -> dict:
    q = """
    MATCH (p {id: $id}) WHERE p:Provider OR p:Seeker OR p:User
    WITH p
    OPTIONAL MATCH (b)
    WHERE any(lbl IN labels(b) WHERE lbl STARTS WITH 'Booking')
      AND b.providerId = $id AND b.status = 'completed'
    WITH p, count(b) AS completedJobs,
         sum(COALESCE(b.finalPrice, b.estimatedPrice, 0)) AS totalEarnings
    OPTIONAL MATCH (cb)
    WHERE any(lbl IN labels(cb) WHERE lbl STARTS WITH 'Booking')
      AND cb.providerId = $id AND cb.status = 'cancelled'
    WITH p, completedJobs, totalEarnings, count(cb) AS cancelledJobs
    OPTIONAL MATCH (f:Feedback {providerId: $id})
    RETURN p.name AS name, p.rating AS rating,
           completedJobs, cancelledJobs, totalEarnings,
           COALESCE(avg(f.rating), 0.0) AS avgRating,
           count(f) AS reviewCount
    """
    rows = run_query(q, {"id": provider_id})
    return rows[0] if rows else {}


def get_top_providers(limit: int = 10) -> list[dict]:
    q = """
    MATCH (p:Provider {isVerified: true})
    OPTIONAL MATCH (b)
    WHERE any(lbl IN labels(b) WHERE lbl STARTS WITH 'Booking')
      AND b.providerId = p.id AND b.status = 'completed'
    WITH p, count(b) AS completedJobs,
         sum(COALESCE(b.finalPrice, b.estimatedPrice, 0)) AS earnings
    RETURN p.id AS id, p.name AS name, COALESCE(p.rating, 0.0) AS rating,
           p.email AS email, completedJobs, earnings
    ORDER BY completedJobs DESC
    LIMIT $limit
    """
    return run_query(q, {"limit": limit})


# ── Bookings ──────────────────────────────────────────────────────────────────

def get_all_bookings(
    status: Optional[str] = None,
    page: int = 0,
    size: int = 50,
    search: Optional[str] = None
) -> list[dict]:
    where_parts = ["any(lbl IN labels(b) WHERE lbl STARTS WITH 'Booking')"]
    params: dict[str, Any] = {"skip": page * size, "limit": size}

    if status and status != "All":
        where_parts.append("b.status = $status")
        params["status"] = status

    if search:
        params["search"] = f"(?i).*{search}.*"
        where_parts.append(
            "(b.seekerName =~ $search OR b.providerName =~ $search OR b.serviceType =~ $search OR b.id =~ $search)"
        )

    where_clause = "WHERE " + " AND ".join(where_parts)

    q = f"""
    MATCH (b)
    {where_clause}
    OPTIONAL MATCH (seeker)
    WHERE (seeker:Seeker OR seeker:Provider OR seeker:User) AND seeker.id = b.seekerId
    OPTIONAL MATCH (provider)
    WHERE (provider:Provider OR provider:Seeker OR provider:User) AND provider.id = b.providerId
    RETURN b.id AS id, b.status AS status,
           b.seekerId AS seekerId,
           COALESCE(b.seekerName, seeker.name, '—') AS seekerName,
           b.providerId AS providerId,
           COALESCE(b.providerName, provider.name, '—') AS providerName,
           b.serviceType AS serviceType,
           b.pickupAddress AS pickupAddress, b.dropAddress AS dropAddress,
           b.estimatedPrice AS estimatedPrice, b.finalPrice AS finalPrice,
           b.distanceInKm AS distanceInKm,
           b.createdAt AS createdAt, b.updatedAt AS updatedAt,
           b.scheduledDateTime AS scheduledDateTime
    ORDER BY b.createdAt DESC
    SKIP $skip LIMIT $limit
    """
    return run_query(q, params)


def get_booking_detail(booking_id: str) -> dict:
    q = """
    MATCH (b {id: $id})
    WHERE any(lbl IN labels(b) WHERE lbl STARTS WITH 'Booking')
    OPTIONAL MATCH (seeker)
    WHERE (seeker:Seeker OR seeker:Provider OR seeker:User) AND seeker.id = b.seekerId
    OPTIONAL MATCH (provider)
    WHERE (provider:Provider OR provider:Seeker OR provider:User) AND provider.id = b.providerId
    RETURN b.id AS id, b.status AS status,
           b.seekerId AS seekerId,
           COALESCE(b.seekerName, seeker.name, '—') AS seekerName,
           seeker.phone AS seekerPhone, seeker.email AS seekerEmail,
           b.providerId AS providerId,
           COALESCE(b.providerName, provider.name, '—') AS providerName,
           provider.phone AS providerPhone, provider.email AS providerEmail,
           b.serviceType AS serviceType,
           b.pickupAddress AS pickupAddress, b.dropAddress AS dropAddress,
           b.pickupLat AS pickupLat, b.pickupLng AS pickupLng,
           b.dropLat AS dropLat, b.dropLng AS dropLng,
           b.estimatedPrice AS estimatedPrice, b.finalPrice AS finalPrice,
           b.distanceInKm AS distanceInKm,
           b.createdAt AS createdAt, b.updatedAt AS updatedAt,
           b.scheduledDateTime AS scheduledDateTime,
           b.cancellationReason AS cancellationReason
    """
    rows = run_query(q, {"id": booking_id})
    return rows[0] if rows else {}


def cancel_booking(booking_id: str, reason: str = "Admin action") -> bool:
    q = """
    MATCH (b {id: $id})
    WHERE any(lbl IN labels(b) WHERE lbl STARTS WITH 'Booking')
    SET b.status = 'cancelled',
        b.cancellationReason = $reason,
        b.updatedAt = datetime()
    RETURN b.id AS id
    """
    rows = run_query(q, {"id": booking_id, "reason": reason}, write=True)
    return bool(rows)


# ── Services ──────────────────────────────────────────────────────────────────

def get_all_services(
    active_only: bool = False,
    page: int = 0,
    size: int = 50,
    category: Optional[str] = None,
    search: Optional[str] = None
) -> list[dict]:
    where_parts = []
    params: dict[str, Any] = {"skip": page * size, "limit": size}

    if active_only:
        where_parts.append("s.isActive = true")

    if category and category != "All":
        params["cat"] = category
        where_parts.append("s.category = $cat")

    if search:
        params["search"] = f"(?i).*{search}.*"
        where_parts.append("(s.name =~ $search OR p.name =~ $search)")

    where_clause = ("WHERE " + " AND ".join(where_parts)) if where_parts else ""

    q = f"""
    MATCH (p:Provider|Seeker)-[:OFFERS]->(s:Service)
    OPTIONAL MATCH (v:Vehicle)-[:PROVIDES]->(s)
    {where_clause}
    RETURN s.id AS id, s.name AS name, s.category AS category,
           s.basePrice AS basePrice, s.pricePerKm AS pricePerKm,
           s.pricePerHour AS pricePerHour, COALESCE(s.isActive, false) AS isActive,
           s.createdAt AS createdAt,
           p.id AS providerId, p.name AS providerName,
           v.vehicleType AS vehicleType, v.vehicleNumber AS vehicleNumber
    ORDER BY s.createdAt DESC
    SKIP $skip LIMIT $limit
    """
    return run_query(q, params)


def toggle_service_status(service_id: str, active: bool) -> bool:
    q = """
    MATCH (s:Service {id: $id})
    SET s.isActive = $active, s.updatedAt = datetime()
    RETURN s.id AS id
    """
    rows = run_query(q, {"id": service_id, "active": active}, write=True)
    return bool(rows)


def delete_service(service_id: str) -> bool:
    q = "MATCH (s:Service {id: $id}) DETACH DELETE s RETURN 1 AS deleted"
    rows = run_query(q, {"id": service_id}, write=True)
    return bool(rows)


# ── Vehicles ──────────────────────────────────────────────────────────────────

def get_all_vehicles(
    page: int = 0,
    size: int = 50,
    type: Optional[str] = None,
    is_available: Optional[bool] = None,
    is_verified: Optional[bool] = None,
    search: Optional[str] = None
) -> list[dict]:
    where_parts = []
    params: dict[str, Any] = {"skip": page * size, "limit": size}

    if type and type != "All":
        params["type"] = type
        where_parts.append("v.vehicleType = $type")

    if is_available is not None:
        params["avail"] = is_available
        where_parts.append("v.isAvailable = $avail")

    if is_verified is not None:
        params["ver"] = is_verified
        where_parts.append("COALESCE(v.isVerified, false) = $ver")

    if search:
        params["search"] = f"(?i).*{search}.*"
        where_parts.append(
            "(v.vehicleNumber =~ $search OR v.vehicleModel =~ $search OR p.name =~ $search)"
        )

    where_clause = ("WHERE " + " AND ".join(where_parts)) if where_parts else ""

    q = f"""
    MATCH (v:Vehicle)
    OPTIONAL MATCH (p)-[:OWNS]->(v)
    WHERE (p:Provider OR p:User OR p:Seeker OR p IS NULL)
    WITH v, p
    {where_clause}
    RETURN v.id AS id, v.vehicleType AS vehicleType,
           v.vehicleNumber AS vehicleNumber, v.vehicleModel AS vehicleModel,
           v.vehicleYear AS vehicleYear, v.capacity AS capacity,
           COALESCE(v.isAvailable, false) AS isAvailable,
           COALESCE(v.isVerified, false) AS isVerified,
           COALESCE(v.addedAfterVerification, false) AS addedAfterVerification,
           COALESCE(v.adminReviewed, false) AS adminReviewed,
           v.createdAt AS createdAt,
           p.id AS providerId, p.name AS providerName,
           COALESCE(p.isVerified, false) AS providerIsVerified
    ORDER BY v.createdAt DESC
    SKIP $skip LIMIT $limit
    """
    return run_query(q, params)


def get_post_verification_vehicles() -> list[dict]:
    q = """
    MATCH (v:Vehicle {addedAfterVerification: true})
    OPTIONAL MATCH (p)-[:OWNS]->(v)
    WHERE p:Provider OR p:User OR p:Seeker
    RETURN v.id AS id, v.vehicleType AS vehicleType,
           v.vehicleNumber AS vehicleNumber, v.vehicleModel AS vehicleModel,
           v.vehicleYear AS vehicleYear, v.capacity AS capacity,
           COALESCE(v.isAvailable, false) AS isAvailable,
           COALESCE(v.isVerified, true) AS isVerified,
           COALESCE(v.adminReviewed, false) AS adminReviewed,
           v.vehicleImageBase64        AS vehicleImageBase64,
           v.vehicleLicenseImageBase64 AS vehicleLicenseImageBase64,
           v.createdAt AS createdAt,
           p.id    AS providerId,
           p.name  AS providerName,
           p.email AS providerEmail,
           p.phone AS providerPhone
    ORDER BY
        COALESCE(v.adminReviewed, false) ASC,
        v.createdAt DESC
    """
    return run_query(q)


def mark_vehicle_reviewed(vehicle_id: str) -> bool:
    q = """
    MATCH (v:Vehicle {id: $id})
    SET v.adminReviewed   = true,
        v.adminReviewedAt = datetime(),
        v.updatedAt       = datetime()
    RETURN v.id AS id
    """
    rows = run_query(q, {"id": vehicle_id}, write=True)
    return bool(rows)


def get_vehicle_detail(vehicle_id: str) -> dict:
    q = """
    MATCH (v:Vehicle {id: $id})
    OPTIONAL MATCH (p)-[:OWNS]->(v)
    WHERE p:Provider OR p:User OR p:Seeker
    RETURN v.id AS id, v.vehicleType AS vehicleType,
           v.vehicleNumber AS vehicleNumber, v.vehicleModel AS vehicleModel,
           v.vehicleYear AS vehicleYear, v.capacity AS capacity,
           COALESCE(v.isAvailable, false) AS isAvailable,
           COALESCE(v.isVerified, false) AS isVerified,
           COALESCE(v.addedAfterVerification, false) AS addedAfterVerification,
           COALESCE(v.adminReviewed, false) AS adminReviewed,
           v.vehicleImageBase64        AS vehicleImageBase64,
           v.vehicleLicenseImageBase64 AS vehicleLicenseImageBase64,
           v.createdAt AS createdAt, v.updatedAt AS updatedAt,
           p.id    AS providerId,   p.name  AS providerName,
           p.email AS providerEmail, p.phone AS providerPhone,
           COALESCE(p.isVerified, false) AS providerIsVerified
    """
    rows = run_query(q, {"id": vehicle_id})
    return rows[0] if rows else {}


# ── Feedback & Complaints ─────────────────────────────────────────────────────

def get_all_feedback(page: int = 0, size: int = 50) -> list[dict]:
    q = """
    MATCH (f:Feedback)
    RETURN f.id AS id, f.bookingId AS bookingId,
           f.providerId AS providerId, f.seekerId AS seekerId,
           COALESCE(f.rating, 0.0) AS rating, f.comment AS comment,
           f.reviewerType AS reviewerType,
           f.createdAt AS createdAt
    ORDER BY f.createdAt DESC
    SKIP $skip LIMIT $limit
    """
    return run_query(q, {"skip": page * size, "limit": size})


# ── Notifications & Activity Stream ───────────────────────────────────────────

def get_recent_activity(limit: int = 20) -> list[dict]:
    q = """
    MATCH (b)
    WHERE any(lbl IN labels(b) WHERE lbl STARTS WITH 'Booking')
    OPTIONAL MATCH (seeker)
    WHERE (seeker:Seeker OR seeker:Provider OR seeker:User) AND seeker.id = b.seekerId
    RETURN 'booking' AS type, b.id AS id,
           b.status AS status,
           COALESCE(b.seekerName, seeker.name, 'Unknown') AS actor,
           COALESCE(b.serviceType, '—') AS detail,
           b.createdAt AS timestamp
    ORDER BY b.createdAt DESC
    LIMIT $limit
    """
    return run_query(q, {"limit": limit})


def get_notifications_all(
    limit: int = 100,
    type: Optional[str] = None,
    is_read: Optional[bool] = None,
    search: Optional[str] = None
) -> list[dict]:
    where_parts = []
    params: dict[str, Any] = {"limit": limit}

    if type and type != "All":
        params["type"] = type
        where_parts.append("n.type = $type")

    if is_read is not None:
        params["isRead"] = is_read
        where_parts.append("n.isRead = $isRead")

    if search:
        params["search"] = f"(?i).*{search}.*"
        where_parts.append("(n.title =~ $search OR n.body =~ $search)")

    where_clause = ("WHERE " + " AND ".join(where_parts)) if where_parts else ""

    q = f"""
    MATCH (n:Notification)
    {where_clause}
    RETURN n.id AS id, n.userId AS userId, n.title AS title,
           n.body AS body, n.type AS type, COALESCE(n.isRead, false) AS isRead,
           n.createdAt AS createdAt
    ORDER BY n.createdAt DESC
    LIMIT $limit
    """
    return run_query(q, params)


def create_notification(
    user_id: str,
    title: str,
    body: str,
    notif_type: str = "admin_notification",
    data: Optional[dict] = None
) -> dict:
    import json
    notif_id = str(uuid.uuid4())
    data_str = json.dumps(data or {})
    q = """
    CREATE (n:Notification {
        id: $id,
        userId: $userId,
        title: $title,
        body: $body,
        type: $type,
        data: $data,
        isRead: false,
        createdAt: datetime()
    })
    RETURN n.id AS id
    """
    rows = run_query(q, {
        "id": notif_id,
        "userId": user_id,
        "title": title,
        "body": body,
        "type": notif_type,
        "data": data_str
    }, write=True)
    return {"id": notif_id, "success": bool(rows)}


# ── Admin User Management ─────────────────────────────────────────────────────

def get_admin_user(username: str) -> Optional[dict]:
    q = """
    MATCH (a:AdminUser {username: $username})
    RETURN a.id AS id, a.username AS username, a.email AS email,
           a.passwordHash AS passwordHash, a.firebaseUid AS firebaseUid,
           a.role AS role, COALESCE(a.isActive, true) AS isActive, a.createdAt AS createdAt
    """
    rows = run_query(q, {"username": username})
    return rows[0] if rows else None


def get_admin_user_by_email(email: str) -> Optional[dict]:
    q = """
    MATCH (a:AdminUser {email: $email})
    RETURN a.id AS id, a.username AS username, a.email AS email,
           a.passwordHash AS passwordHash, a.firebaseUid AS firebaseUid,
           a.role AS role, COALESCE(a.isActive, true) AS isActive, a.createdAt AS createdAt
    """
    rows = run_query(q, {"email": email})
    return rows[0] if rows else None


def get_admin_user_by_firebase_uid(uid: str) -> Optional[dict]:
    q = """
    MATCH (a:AdminUser {firebaseUid: $uid})
    RETURN a.id AS id, a.username AS username, a.email AS email,
           a.passwordHash AS passwordHash, a.firebaseUid AS firebaseUid,
           a.role AS role, COALESCE(a.isActive, true) AS isActive, a.createdAt AS createdAt
    """
    rows = run_query(q, {"uid": uid})
    return rows[0] if rows else None


def create_admin_user(
    username: str,
    email: str,
    password_hash: str,
    firebase_uid: Optional[str] = None,
) -> bool:
    node_id = str(uuid.uuid4())
    q = """
    MERGE (a:AdminUser {username: $username})
    ON CREATE SET
        a.id           = $id,
        a.email        = $email,
        a.passwordHash = $passwordHash,
        a.firebaseUid  = $firebaseUid,
        a.role         = 'admin',
        a.isActive     = true,
        a.createdAt    = datetime()
    ON MATCH SET
        a.email        = $email,
        a.passwordHash = $passwordHash,
        a.firebaseUid  = COALESCE($firebaseUid, a.firebaseUid),
        a.updatedAt    = datetime()
    RETURN a.id AS id
    """
    rows = run_query(q, {
        "username": username, "email": email,
        "passwordHash": password_hash,
        "firebaseUid": firebase_uid,
        "id": node_id,
    }, write=True)
    return bool(rows)


def update_admin_password(username: str, password_hash: str) -> bool:
    q = """
    MATCH (a:AdminUser {username: $username})
    SET a.passwordHash = $hash, a.updatedAt = datetime()
    RETURN a.id AS id
    """
    rows = run_query(q, {"username": username, "hash": password_hash}, write=True)
    return bool(rows)


def admin_user_count() -> int:
    q = "MATCH (a:AdminUser) RETURN count(a) AS total"
    rows = run_query(q)
    return int(rows[0].get("total", 0)) if rows else 0


def get_all_admin_users() -> list[dict]:
    q = """
    MATCH (a:AdminUser)
    RETURN a.id AS id, a.username AS username, a.email AS email,
           a.role AS role, COALESCE(a.isActive, true) AS isActive, a.createdAt AS createdAt
    ORDER BY a.createdAt ASC
    """
    return run_query(q)


def toggle_admin_user(admin_id: str, active: bool) -> bool:
    q = """
    MATCH (a:AdminUser {id: $id})
    SET a.isActive = $active, a.updatedAt = datetime()
    RETURN a.id AS id
    """
    rows = run_query(q, {"id": admin_id, "active": active}, write=True)
    return bool(rows)


def delete_admin_user(admin_id: str) -> bool:
    q = "MATCH (a:AdminUser {id: $id}) DELETE a RETURN count(*) AS deleted"
    rows = run_query(q, {"id": admin_id}, write=True)
    return bool(rows)


# ── Provider Transactions & Earnings ──────────────────────────────────────────

def get_all_providers_earnings(page: int = 0, size: int = 100) -> list[dict]:
    commission_rate = admin_settings.PLATFORM_COMMISSION_RATE
    q = f"""
    MATCH (p:Provider)
    OPTIONAL MATCH (cb)
    WHERE any(lbl IN labels(cb) WHERE lbl STARTS WITH 'Booking')
      AND cb.providerId = p.id AND cb.status = 'completed'
    WITH p,
         count(cb) AS completedBookings,
         sum(COALESCE(cb.finalPrice, cb.estimatedPrice, 0)) AS grossEarnings
    OPTIONAL MATCH (pb)
    WHERE any(lbl IN labels(pb) WHERE lbl STARTS WITH 'Booking')
      AND pb.providerId = p.id
      AND pb.status IN ['accepted','active','in_progress',
                        'provider_arriving','provider_arrived']
    WITH p, completedBookings, grossEarnings,
         count(pb)  AS pendingBookings,
         sum(COALESCE(pb.estimatedPrice, 0)) AS pendingValue
    RETURN p.id          AS providerId,
           p.name        AS providerName,
           p.email       AS providerEmail,
           COALESCE(p.isVerified, false) AS isVerified,
           COALESCE(p.isActive, false) AS isActive,
           completedBookings,
           grossEarnings,
           grossEarnings * {commission_rate} AS commission,
           grossEarnings * {1 - commission_rate} AS netEarnings,
           pendingBookings,
           pendingValue
    ORDER BY grossEarnings DESC
    SKIP $skip LIMIT $limit
    """
    return run_query(q, {"skip": page * size, "limit": size})


def get_provider_earnings_summary(provider_id: str) -> dict:
    commission_rate = admin_settings.PLATFORM_COMMISSION_RATE
    q = f"""
    MATCH (p) WHERE (p:Provider OR p:Seeker) AND p.id = $id
    OPTIONAL MATCH (cb)
    WHERE any(lbl IN labels(cb) WHERE lbl STARTS WITH 'Booking')
      AND cb.providerId = $id AND cb.status = 'completed'
    WITH p,
         count(cb) AS completedBookings,
         sum(COALESCE(cb.finalPrice, cb.estimatedPrice, 0)) AS grossEarnings
    OPTIONAL MATCH (pb)
    WHERE any(lbl IN labels(pb) WHERE lbl STARTS WITH 'Booking')
      AND pb.providerId = $id
      AND pb.status IN ['accepted','active','in_progress',
                        'provider_arriving','provider_arrived']
    WITH p, completedBookings, grossEarnings,
         count(pb)  AS pendingBookings,
         sum(COALESCE(pb.estimatedPrice, 0)) AS pendingValue
    OPTIONAL MATCH (ab)
    WHERE any(lbl IN labels(ab) WHERE lbl STARTS WITH 'Booking')
      AND ab.providerId = $id
    OPTIONAL MATCH (xb)
    WHERE any(lbl IN labels(xb) WHERE lbl STARTS WITH 'Booking')
      AND xb.providerId = $id AND xb.status = 'cancelled'
    RETURN p.name       AS name,
           p.email      AS email,
           COALESCE(p.isVerified, false) AS isVerified,
           completedBookings,
           grossEarnings,
           grossEarnings * {commission_rate} AS commission,
           grossEarnings * {1 - commission_rate} AS netEarnings,
           pendingBookings,
           pendingValue,
           count(DISTINCT ab) AS totalBookings,
           count(DISTINCT xb) AS cancelledBookings
    """
    rows = run_query(q, {"id": provider_id})
    return rows[0] if rows else {}


def get_provider_transactions(
    provider_id: str, page: int = 0, size: int = 50, status: Optional[str] = None
) -> list[dict]:
    status_filter = "AND b.status = $status" if status else ""
    q = f"""
    MATCH (b)
    WHERE any(lbl IN labels(b) WHERE lbl STARTS WITH 'Booking')
      AND b.providerId = $id {status_filter}
    OPTIONAL MATCH (sk)
    WHERE (sk:Seeker OR sk:User) AND sk.id = b.seekerId
    RETURN b.id        AS id,
           b.status    AS status,
           b.serviceType AS serviceType,
           COALESCE(b.seekerName, sk.name, '—') AS seekerName,
           COALESCE(b.finalPrice, b.estimatedPrice, 0) AS amount,
           b.finalPrice      AS finalPrice,
           b.estimatedPrice  AS estimatedPrice,
           b.distanceInKm    AS distanceKm,
           b.pickupAddress   AS pickupAddress,
           b.createdAt       AS createdAt,
           b.updatedAt       AS updatedAt
    ORDER BY b.createdAt DESC
    SKIP $skip LIMIT $limit
    """
    params: dict[str, Any] = {"id": provider_id, "skip": page * size, "limit": size}
    if status:
        params["status"] = status
    return run_query(q, params)


def get_provider_monthly_earnings(provider_id: str, months: int = 12) -> list[dict]:
    q = """
    MATCH (b)
    WHERE any(lbl IN labels(b) WHERE lbl STARTS WITH 'Booking')
      AND b.providerId = $id
      AND b.status = 'completed'
      AND b.updatedAt >= datetime() - duration({months: $months})
    RETURN date.truncate('month', date(b.updatedAt)) AS month,
           count(b) AS bookings,
           sum(COALESCE(b.finalPrice, b.estimatedPrice, 0)) AS revenue
    ORDER BY month ASC
    """
    return run_query(q, {"id": provider_id, "months": months})


def count_provider_transactions(provider_id: str, status: Optional[str] = None) -> int:
    status_filter = "AND b.status = $status" if status else ""
    q = f"""
    MATCH (b)
    WHERE any(lbl IN labels(b) WHERE lbl STARTS WITH 'Booking')
      AND b.providerId = $id {status_filter}
    RETURN count(b) AS total
    """
    params: dict[str, Any] = {"id": provider_id}
    if status:
        params["status"] = status
    rows = run_query(q, params)
    return int(rows[0].get("total", 0)) if rows else 0
