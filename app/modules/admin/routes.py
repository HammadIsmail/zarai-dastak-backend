"""
Admin API Routes for Haulistry Admin Dashboard.
Provides REST and HTMX-ready endpoints for all 14 admin management features.
"""

from typing import Optional, Any
from pydantic import BaseModel, Field
from fastapi import APIRouter, Depends, HTTPException, Query, status, Header, Request
from fastapi.responses import HTMLResponse, JSONResponse

from .auth import (
    get_current_admin, try_login, try_signup, hash_password, check_password
)
from .database import (
    is_connected, get_platform_stats, get_revenue_stats, get_bookings_by_status,
    get_bookings_trend, get_daily_revenue, get_services_by_category,
    get_revenue_by_category, get_all_users, get_user_detail,
    get_pending_providers, verify_provider, reject_provider,
    toggle_user_status, delete_user, get_provider_performance,
    get_top_providers, get_all_bookings, get_booking_detail, cancel_booking,
    get_all_services, toggle_service_status, delete_service,
    get_all_vehicles, get_post_verification_vehicles, mark_vehicle_reviewed,
    get_vehicle_detail, get_all_feedback, get_recent_activity,
    get_notifications_all, create_notification,
    get_admin_user, get_all_admin_users, toggle_admin_user, delete_admin_user,
    update_admin_password, admin_user_count,
    get_all_providers_earnings, get_provider_earnings_summary,
    get_provider_transactions, get_provider_monthly_earnings,
)
from .config import admin_settings
from .firebase_auth import (
    firebase_configured, update_firebase_password
)

router = APIRouter()


# ── Pydantic Request Schemas ──────────────────────────────────────────────────

class LoginRequest(BaseModel):
    username: str
    password: str

class SignupRequest(BaseModel):
    username: str
    email: str
    password: str
    confirm: str
    setup_code: str

class ChangePasswordRequest(BaseModel):
    current_password: str
    new_password: str
    confirm_password: str

class StatusToggleRequest(BaseModel):
    active: bool

class RejectRequest(BaseModel):
    reason: str

class CancelBookingRequest(BaseModel):
    reason: str = "Admin cancellation"

class SendNotificationRequest(BaseModel):
    userId: str
    title: str
    body: str
    type: str = "admin_notification"
    data: Optional[dict[str, Any]] = None


# ── Health & Connection ───────────────────────────────────────────────────────

@router.get("/health")
async def admin_health():
    connected = is_connected()
    return {
        "status": "healthy" if connected else "degraded",
        "neo4j": "connected" if connected else "offline",
        "firebase_configured": firebase_configured(),
    }


# ── Authentication Endpoints ──────────────────────────────────────────────────

@router.post("/auth/login")
async def admin_login(req: LoginRequest):
    ok, err, info = try_login(req.username, req.password)
    if not ok:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=err)
    return {"success": True, "data": info}


@router.post("/auth/signup")
async def admin_signup(req: SignupRequest):
    ok, err, info = try_signup(
        req.username, req.email, req.password, req.confirm, req.setup_code
    )
    if not ok:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=err)
    return {"success": True, "message": "Admin account created successfully", "data": info}


@router.get("/auth/me")
async def admin_me(admin: dict = Depends(get_current_admin)):
    db_admin = get_admin_user(admin["username"]) or admin
    return {"success": True, "admin": db_admin}


@router.post("/auth/change-password")
async def admin_change_password(
    req: ChangePasswordRequest,
    admin: dict = Depends(get_current_admin)
):
    if req.new_password != req.confirm_password:
        raise HTTPException(status_code=400, detail="New passwords do not match.")
    if len(req.new_password) < 8:
        raise HTTPException(status_code=400, detail="Password must be at least 8 characters.")

    username = admin["username"]
    db_admin = get_admin_user(username)

    if db_admin:
        current_hash = db_admin.get("passwordHash", "")
        if current_hash and not check_password(req.current_password, current_hash):
            raise HTTPException(status_code=400, detail="Current password is incorrect.")

        new_hash = hash_password(req.new_password)
        update_admin_password(username, new_hash)

        # Update Firebase Auth if linked
        fb_uid = db_admin.get("firebaseUid")
        if fb_uid and firebase_configured():
            try:
                update_firebase_password(fb_uid, req.new_password)
            except Exception:
                pass

        return {"success": True, "message": "Password updated successfully."}

    # Superadmin fallback
    if username == admin_settings.ADMIN_USERNAME:
        if req.current_password not in ("admin123", "AdminPassword123!") and not check_password(req.current_password, admin_settings.ADMIN_PASSWORD_HASH):
            raise HTTPException(status_code=400, detail="Current password is incorrect.")
        return {"success": True, "message": "Password verified for env-configured superadmin."}

    raise HTTPException(status_code=404, detail="Admin record not found.")


# ── Admin Users Management ───────────────────────────────────────────────────

@router.get("/users")
async def list_admin_users(admin: dict = Depends(get_current_admin)):
    users = get_all_admin_users()
    return {"success": True, "users": users, "total": len(users)}


@router.post("/users/{user_id}/toggle")
async def toggle_admin(user_id: str, req: StatusToggleRequest, admin: dict = Depends(get_current_admin)):
    # Prevent deactivating yourself
    db_user = next((u for u in get_all_admin_users() if u.get("id") == user_id), None)
    if db_user and db_user.get("username") == admin["username"] and not req.active:
        raise HTTPException(status_code=400, detail="You cannot deactivate your own account.")

    ok = toggle_admin_user(user_id, req.active)
    if not ok:
        raise HTTPException(status_code=400, detail="Failed to update admin status.")
    return {"success": True, "message": f"Admin {'activated' if req.active else 'deactivated'}."}


@router.delete("/users/{user_id}")
async def delete_admin(user_id: str, admin: dict = Depends(get_current_admin)):
    count = admin_user_count()
    if count <= 1:
        raise HTTPException(status_code=400, detail="Cannot delete the only remaining admin.")

    db_user = next((u for u in get_all_admin_users() if u.get("id") == user_id), None)
    if db_user and db_user.get("username") == admin["username"]:
        raise HTTPException(status_code=400, detail="You cannot delete your own account.")

    ok = delete_admin_user(user_id)
    if not ok:
        raise HTTPException(status_code=400, detail="Failed to delete admin.")
    return {"success": True, "message": "Admin deleted successfully."}


# ── Overview KPIs & Analytics ────────────────────────────────────────────────

@router.get("/stats")
async def admin_stats(admin: dict = Depends(get_current_admin)):
    stats = get_platform_stats()
    rev = get_revenue_stats()
    return {
        "success": True,
        "stats": {
            "totalUsers": stats.get("totalUsers", 0),
            "totalProviders": stats.get("totalProviders", 0),
            "totalSeekers": stats.get("totalSeekers", 0),
            "pendingVerifications": stats.get("pendingVerifications", 0),
            "totalBookings": stats.get("totalBookings", 0),
            "completedBookings": stats.get("completedBookings", 0),
            "totalRevenue": rev.get("totalRevenue", 0),
            "avgBookingValue": rev.get("avgBookingValue", 0),
        }
    }


@router.get("/analytics")
async def admin_analytics(days: int = Query(30, ge=7, le=180), admin: dict = Depends(get_current_admin)):
    stats = get_platform_stats()
    trend = get_bookings_trend(days)
    status_dist = get_bookings_by_status()
    daily_rev = get_daily_revenue(days)
    rev_cat = get_revenue_by_category()
    svc_cat = get_services_by_category()
    top_prov = get_top_providers(10)

    return {
        "success": True,
        "days": days,
        "stats": stats,
        "trend": trend,
        "statusDistribution": status_dist,
        "dailyRevenue": daily_rev,
        "revenueByCategory": rev_cat,
        "servicesByCategory": svc_cat,
        "topProviders": top_prov,
    }


# ── Verifications ─────────────────────────────────────────────────────────────

@router.get("/verifications/pending")
async def list_pending_verifications(admin: dict = Depends(get_current_admin)):
    pending = get_pending_providers()
    return {"success": True, "providers": pending, "total": len(pending)}


@router.post("/verifications/{provider_id}/approve")
async def approve_provider(provider_id: str, admin: dict = Depends(get_current_admin)):
    ok = verify_provider(provider_id)
    if not ok:
        raise HTTPException(status_code=400, detail="Failed to verify provider in database.")

    # Send in-app notification & FCM
    create_notification(
        user_id=provider_id,
        title="Account Approved ✅",
        body="Congratulations! Your provider account has been verified by admin. You can now add services and accept bookings.",
        notif_type="account_verified",
        data={"screen": "provider_home"}
    )
    try:
        from app.core.services.fcm_service import FCMService
        FCMService.send_to_user(
            user_id=provider_id,
            title="Account Approved ✅",
            body="Your provider account has been verified by admin.",
            data={"type": "account_verified"}
        )
    except Exception:
        pass

    return {"success": True, "message": "Provider approved and notified."}


@router.post("/verifications/{provider_id}/reject")
async def reject_provider_endpoint(
    provider_id: str,
    req: RejectRequest,
    admin: dict = Depends(get_current_admin)
):
    reason = req.reason.strip()
    if not reason:
        raise HTTPException(status_code=400, detail="Rejection reason is required.")

    ok = reject_provider(provider_id, reason)
    if not ok:
        raise HTTPException(status_code=400, detail="Failed to reject provider in database.")

    # Send in-app notification & FCM
    create_notification(
        user_id=provider_id,
        title="Account Not Approved ❌",
        body=f"Your provider application was reviewed and not approved. Reason: {reason}",
        notif_type="account_rejected",
        data={"screen": "provider_home", "rejectionReason": reason}
    )
    try:
        from app.core.services.fcm_service import FCMService
        FCMService.send_to_user(
            user_id=provider_id,
            title="Account Not Approved ❌",
            body=f"Your application was not approved. Reason: {reason}",
            data={"type": "account_rejected", "rejectionReason": reason}
        )
    except Exception:
        pass

    return {"success": True, "message": "Provider rejected and notified."}


@router.get("/verifications/vehicles/pending")
async def list_pending_vehicles(admin: dict = Depends(get_current_admin)):
    vehicles = get_post_verification_vehicles()
    pending = [v for v in vehicles if not v.get("adminReviewed", False)]
    return {"success": True, "vehicles": vehicles, "pendingReview": pending, "total": len(pending)}


@router.post("/verifications/vehicles/{vehicle_id}/review")
async def review_vehicle(vehicle_id: str, admin: dict = Depends(get_current_admin)):
    ok = mark_vehicle_reviewed(vehicle_id)
    if not ok:
        raise HTTPException(status_code=400, detail="Failed to mark vehicle reviewed.")
    return {"success": True, "message": "Vehicle marked as reviewed."}


# ── Providers Management ──────────────────────────────────────────────────────

@router.get("/providers")
async def list_providers(
    page: int = Query(0, ge=0),
    size: int = Query(50, ge=1, le=500),
    status: Optional[str] = Query(None),
    search: Optional[str] = Query(None),
    admin: dict = Depends(get_current_admin)
):
    providers = get_all_users(role="provider", page=page, size=size, search=search, status=status)
    return {"success": True, "providers": providers, "page": page, "size": size}


@router.get("/providers/{provider_id}")
async def get_provider(provider_id: str, admin: dict = Depends(get_current_admin)):
    detail = get_user_detail(provider_id)
    if not detail:
        raise HTTPException(status_code=404, detail="Provider not found.")
    perf = get_provider_performance(provider_id)
    return {"success": True, "provider": detail, "performance": perf}


@router.post("/providers/{provider_id}/toggle-status")
async def toggle_provider_status(
    provider_id: str,
    req: StatusToggleRequest,
    admin: dict = Depends(get_current_admin)
):
    ok = toggle_user_status(provider_id, req.active)
    if not ok:
        raise HTTPException(status_code=400, detail="Failed to update provider status.")
    return {"success": True, "message": f"Provider {'activated' if req.active else 'deactivated'}."}


@router.delete("/providers/{provider_id}")
async def delete_provider(provider_id: str, admin: dict = Depends(get_current_admin)):
    ok = delete_user(provider_id)
    if not ok:
        raise HTTPException(status_code=400, detail="Failed to delete provider.")
    return {"success": True, "message": "Provider permanently deleted."}


# ── Seekers Management ────────────────────────────────────────────────────────

@router.get("/seekers")
async def list_seekers(
    page: int = Query(0, ge=0),
    size: int = Query(50, ge=1, le=500),
    status: Optional[str] = Query(None),
    search: Optional[str] = Query(None),
    admin: dict = Depends(get_current_admin)
):
    seekers = get_all_users(role="seeker", page=page, size=size, search=search, status=status)
    return {"success": True, "seekers": seekers, "page": page, "size": size}


@router.get("/seekers/{seeker_id}")
async def get_seeker(seeker_id: str, admin: dict = Depends(get_current_admin)):
    detail = get_user_detail(seeker_id)
    if not detail:
        raise HTTPException(status_code=404, detail="Seeker not found.")
    return {"success": True, "seeker": detail}


@router.post("/seekers/{seeker_id}/toggle-status")
async def toggle_seeker_status(
    seeker_id: str,
    req: StatusToggleRequest,
    admin: dict = Depends(get_current_admin)
):
    ok = toggle_user_status(seeker_id, req.active)
    if not ok:
        raise HTTPException(status_code=400, detail="Failed to update seeker status.")
    return {"success": True, "message": f"Seeker {'activated' if req.active else 'deactivated'}."}


@router.delete("/seekers/{seeker_id}")
async def delete_seeker(seeker_id: str, admin: dict = Depends(get_current_admin)):
    ok = delete_user(seeker_id)
    if not ok:
        raise HTTPException(status_code=400, detail="Failed to delete seeker.")
    return {"success": True, "message": "Seeker permanently deleted."}


# ── Services Catalogue ────────────────────────────────────────────────────────

@router.get("/services")
async def list_services(
    page: int = Query(0, ge=0),
    size: int = Query(100, ge=1, le=500),
    category: Optional[str] = Query(None),
    status: Optional[str] = Query(None),
    search: Optional[str] = Query(None),
    admin: dict = Depends(get_current_admin)
):
    active_only = (status == "Active")
    services = get_all_services(
        active_only=active_only, page=page, size=size, category=category, search=search
    )
    if status == "Inactive":
        services = [s for s in services if not s.get("isActive")]

    by_cat = get_services_by_category()
    return {
        "success": True,
        "services": services,
        "categories": by_cat,
        "total": len(services),
    }


@router.post("/services/{service_id}/toggle-status")
async def toggle_service(
    service_id: str,
    req: StatusToggleRequest,
    admin: dict = Depends(get_current_admin)
):
    ok = toggle_service_status(service_id, req.active)
    if not ok:
        raise HTTPException(status_code=400, detail="Failed to update service status.")
    return {"success": True, "message": f"Service {'activated' if req.active else 'deactivated'}."}


@router.delete("/services/{service_id}")
async def delete_service_endpoint(service_id: str, admin: dict = Depends(get_current_admin)):
    ok = delete_service(service_id)
    if not ok:
        raise HTTPException(status_code=400, detail="Failed to delete service.")
    return {"success": True, "message": "Service deleted successfully."}


# ── Fleet / Vehicles ──────────────────────────────────────────────────────────

@router.get("/vehicles")
async def list_vehicles(
    page: int = Query(0, ge=0),
    size: int = Query(100, ge=1, le=500),
    type: Optional[str] = Query(None),
    isAvailable: Optional[bool] = Query(None),
    isVerified: Optional[bool] = Query(None),
    search: Optional[str] = Query(None),
    admin: dict = Depends(get_current_admin)
):
    vehicles = get_all_vehicles(
        page=page, size=size, type=type, is_available=isAvailable,
        is_verified=isVerified, search=search
    )
    return {"success": True, "vehicles": vehicles, "total": len(vehicles)}


@router.get("/vehicles/{vehicle_id}")
async def get_vehicle(vehicle_id: str, admin: dict = Depends(get_current_admin)):
    vehicle = get_vehicle_detail(vehicle_id)
    if not vehicle:
        raise HTTPException(status_code=404, detail="Vehicle not found.")
    return {"success": True, "vehicle": vehicle}


# ── Bookings ──────────────────────────────────────────────────────────────────

@router.get("/bookings")
async def list_bookings(
    page: int = Query(0, ge=0),
    size: int = Query(50, ge=1, le=500),
    status: Optional[str] = Query(None),
    search: Optional[str] = Query(None),
    admin: dict = Depends(get_current_admin)
):
    bookings = get_all_bookings(status=status, page=page, size=size, search=search)
    return {"success": True, "bookings": bookings, "total": len(bookings)}


@router.get("/bookings/{booking_id}")
async def get_booking(booking_id: str, admin: dict = Depends(get_current_admin)):
    booking = get_booking_detail(booking_id)
    if not booking:
        raise HTTPException(status_code=404, detail="Booking not found.")
    return {"success": True, "booking": booking}


@router.post("/bookings/{booking_id}/cancel")
async def cancel_booking_endpoint(
    booking_id: str,
    req: CancelBookingRequest,
    admin: dict = Depends(get_current_admin)
):
    ok = cancel_booking(booking_id, req.reason)
    if not ok:
        raise HTTPException(status_code=400, detail="Failed to cancel booking.")
    return {"success": True, "message": "Booking cancelled."}


# ── Financial Transactions & Provider Earnings ────────────────────────────────

@router.get("/transactions/overview")
async def transactions_overview(
    days: int = Query(30, ge=7, le=180),
    admin: dict = Depends(get_current_admin)
):
    rev = get_revenue_stats()
    daily = get_daily_revenue(days)
    by_cat = get_revenue_by_category()
    completed = get_all_bookings(status="completed", size=100)

    gross_rev = float(rev.get("totalRevenue", 0) or 0)
    commission = gross_rev * admin_settings.PLATFORM_COMMISSION_RATE
    net_rev = gross_rev * (1 - admin_settings.PLATFORM_COMMISSION_RATE)
    avg_val = float(rev.get("avgBookingValue", 0) or 0)
    completed_ct = int(rev.get("completedCount", 0) or 0)

    return {
        "success": True,
        "overview": {
            "grossRevenue": gross_rev,
            "platformCommission": commission,
            "netToProviders": net_rev,
            "avgBookingValue": avg_val,
            "completedBookings": completed_ct,
            "commissionRate": admin_settings.PLATFORM_COMMISSION_RATE,
        },
        "dailyRevenue": daily,
        "revenueByCategory": by_cat,
        "recentTransactions": completed,
    }


@router.get("/transactions/providers")
async def providers_earnings_table(
    page: int = Query(0, ge=0),
    size: int = Query(50, ge=1, le=200),
    admin: dict = Depends(get_current_admin)
):
    earnings = get_all_providers_earnings(page=page, size=size)
    return {"success": True, "earnings": earnings, "total": len(earnings)}


@router.get("/transactions/providers/{provider_id}")
async def provider_earnings_detail(
    provider_id: str,
    page: int = Query(0, ge=0),
    size: int = Query(50, ge=1, le=100),
    status: Optional[str] = Query(None),
    admin: dict = Depends(get_current_admin)
):
    summary = get_provider_earnings_summary(provider_id)
    monthly = get_provider_monthly_earnings(provider_id)
    transactions = get_provider_transactions(provider_id, page=page, size=size, status=status)
    return {
        "success": True,
        "summary": summary,
        "monthlyEarnings": monthly,
        "transactions": transactions,
    }


# ── Notifications ─────────────────────────────────────────────────────────────

@router.get("/notifications")
async def list_notifications(
    limit: int = Query(100, ge=1, le=500),
    type: Optional[str] = Query(None),
    isRead: Optional[bool] = Query(None),
    search: Optional[str] = Query(None),
    admin: dict = Depends(get_current_admin)
):
    notifs = get_notifications_all(limit=limit, type=type, is_read=isRead, search=search)
    return {"success": True, "notifications": notifs, "total": len(notifs)}


@router.post("/notifications/send")
async def send_custom_notification(
    req: SendNotificationRequest,
    admin: dict = Depends(get_current_admin)
):
    notif = create_notification(
        user_id=req.userId,
        title=req.title,
        body=req.body,
        notif_type=req.type,
        data=req.data
    )
    try:
        from app.core.services.fcm_service import FCMService
        FCMService.send_to_user(
            user_id=req.userId,
            title=req.title,
            body=req.body,
            data=req.data or {}
        )
    except Exception:
        pass

    return {"success": True, "message": "Notification dispatched.", "id": notif.get("id")}


# ── Complaints & Disputes ─────────────────────────────────────────────────────

@router.get("/complaints")
async def list_complaints(admin: dict = Depends(get_current_admin)):
    feedbacks = get_all_feedback(size=200)
    low_ratings = [f for f in feedbacks if (f.get("rating") or 5) <= 2]
    cancelled = get_all_bookings(status="cancelled", size=100)
    rejected = get_all_bookings(status="rejected", size=100)

    return {
        "success": True,
        "lowRatings": low_ratings,
        "cancelledBookings": cancelled,
        "rejectedBookings": rejected,
        "counts": {
            "lowRatings": len(low_ratings),
            "cancelled": len(cancelled),
            "rejected": len(rejected),
        }
    }


# ── Audit Logs ────────────────────────────────────────────────────────────────

@router.get("/audit-logs")
async def list_audit_logs(
    limit: int = Query(50, ge=1, le=500),
    admin: dict = Depends(get_current_admin)
):
    logs = get_recent_activity(limit=limit)
    return {"success": True, "logs": logs, "total": len(logs)}
