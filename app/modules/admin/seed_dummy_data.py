"""
Comprehensive Seed Script for Haulistry Admin Dashboard Testing.
Generates realistic dummy data for EVERY admin case:
- Platform KPIs
- Pending Provider Verifications with document base64
- Post-verification vehicle additions needing review
- Active & Inactive Providers with linked vehicles and services
- Active & Inactive Seekers
- Services Catalogue across all machinery categories
- Fleet Registry across vehicle types
- Bookings across all status flows over last 30-60 days
- Low-rated reviews (1 & 2 stars) for Complaints testing
- Cancelled & Rejected Bookings with reasons
- In-App Notifications across types
- Additional Admin Accounts
"""

import sys
import uuid
from datetime import datetime, timedelta
import random

from app.core.database.neo4j_driver import neo4j_driver
from .auth import hash_password

# Sample Base64 image with a readable document stamp (PNG format)
SAMPLE_CNIC_FRONT = (
    "iVBORw0KGgoAAAANSUhEUgAAASwAAACgCAYAAABYGJYCAAAAAXNSR0IArs4c6QAAAARnQU1BAACx"
    "jwv8YQUAAAAJcEhZcwAADsMAAA7DAcdvqGQAAAC0SURBVHhe7cExAQAAAMKg9U9tDQ8gAAAAAAAA"
    "AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA"
    "AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA"
    "AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAADwMoVwAAR5p9b0AAAAASUVO"
    "RK5CYII="
)

SAMPLE_DOC = SAMPLE_CNIC_FRONT


def seed_all():
    print("Starting comprehensive database seeding for Haulistry Admin...")

    with neo4j_driver.get_session() as session:

        # ── 1. Admin Users ────────────────────────────────────────────────────
        print("1. Creating Admin accounts...")
        admin_pass = hash_password("AdminPassword123!")
        admins = [
            ("admin", "admin@haulistry.com", "superadmin", True),
            ("sarah_ops", "sarah.ops@haulistry.com", "admin", True),
            ("khalid_compliance", "khalid.c@haulistry.com", "admin", True),
            ("deactivated_admin", "inactive@haulistry.com", "admin", False),
        ]
        for uname, email, role, active in admins:
            session.run("""
            MERGE (a:AdminUser {username: $username})
            SET a.id = coalesce(a.id, $id),
                a.email = $email,
                a.passwordHash = $pwd,
                a.role = $role,
                a.isActive = $active,
                a.createdAt = datetime() - duration({days: 60})
            """, {
                "id": str(uuid.uuid4()),
                "username": uname,
                "email": email,
                "pwd": admin_pass,
                "role": role,
                "active": active,
            })

        # ── 2. Pending Providers (Awaiting Verification) ──────────────────────
        print("2. Creating Pending Providers for Verifications review...")
        pending_provs = [
            ("Tariq Heavy Cranes", "tariq.cranes@gmail.com", "+92 300 1234567", "35201-1234567-1"),
            ("Rashid Towing Fleet", "rashid.towing@yahoo.com", "+92 321 9876543", "35202-9876543-3"),
            ("Malik Bulldozer Services", "malik.earthmoving@gmail.com", "+92 333 4567890", "35201-4567890-5"),
        ]
        for name, email, phone, cnic in pending_provs:
            pid = str(uuid.uuid4())
            vid = str(uuid.uuid4())
            session.run("""
            MERGE (p:Provider {email: $email})
            ON CREATE SET
                p.id = $pid,
                p.name = $name,
                p.phone = $phone,
                p.cnic = $cnic,
                p.role = 'provider',
                p.isVerified = false,
                p.isActive = false,
                p.rating = 0.0,
                p.cnicFrontImageBase64 = $doc,
                p.cnicBackImageBase64 = $doc,
                p.licenseImageBase64 = $doc,
                p.createdAt = datetime() - duration({days: 2})
            WITH p
            CREATE (v:Vehicle {
                id: $vid,
                vehicleType: 'crane',
                vehicleNumber: 'LHR-7890',
                vehicleModel: 'Kato 25 Ton Crane',
                vehicleYear: 2021,
                capacity: '25 Ton',
                isAvailable: false,
                isVerified: false,
                vehicleImageBase64: $doc,
                createdAt: datetime() - duration({days: 2})
            })
            MERGE (p)-[:OWNS]->(v)
            """, {
                "pid": pid, "vid": vid, "name": name,
                "email": email, "phone": phone, "cnic": cnic,
                "doc": SAMPLE_DOC
            })

        # ── 3. Active & Verified Providers ───────────────────────────────────
        print("3. Creating Active Verified Providers...")
        verified_provs = [
            ("Imran Khan Logistics", "imran.khan@logistics.pk", "+92 301 5551234", 4.9, "35201-9988771-1"),
            ("Punjab Recovery & Towing", "punjab.recovery@gmail.com", "+92 322 4445566", 4.7, "35202-8877662-3"),
            ("Indus Heavy Excavators", "indus.heavy@yahoo.com", "+92 334 3332211", 4.8, "35201-7766553-5"),
            ("Lahore Industrial Cranes", "lahore.cranes@pk.com", "+92 312 9998877", 4.6, "35201-6655444-7"),
            ("Zubair Harvester Services", "zubair.harvester@gmail.com", "+92 305 7776655", 4.3, "35202-5544335-9"),
            ("Bilal Sand Trolley Transport", "bilal.sand@gmail.com", "+92 308 1112233", 3.9, "35201-4433226-1"),
            ("Inactive Provider Ltd", "inactive.provider@haulistry.com", "+92 300 0000000", 3.5, "35201-0000000-0"),
        ]

        provider_ids = {}
        for idx, (name, email, phone, rating, cnic) in enumerate(verified_provs):
            pid = str(uuid.uuid4())
            is_active = (name != "Inactive Provider Ltd")
            session.run("""
            MERGE (p:Provider {email: $email})
            ON CREATE SET
                p.id = $pid,
                p.name = $name,
                p.phone = $phone,
                p.cnic = $cnic,
                p.role = 'provider',
                p.isVerified = true,
                p.isActive = $active,
                p.rating = $rating,
                p.cnicFrontImageBase64 = $doc,
                p.cnicBackImageBase64 = $doc,
                p.licenseImageBase64 = $doc,
                p.createdAt = datetime() - duration({days: $daysAgo}),
                p.verifiedAt = datetime() - duration({days: $daysAgo - 1})
            """, {
                "pid": pid, "name": name, "email": email, "phone": phone,
                "cnic": cnic, "rating": rating, "active": is_active,
                "doc": SAMPLE_DOC, "daysAgo": 90 - (idx * 10)
            })
            # Retrieve or keep ID
            rec = session.run("MATCH (p:Provider {email: $email}) RETURN p.id AS id", {"email": email}).single()
            if rec:
                provider_ids[name] = rec["id"]

        # ── 4. Vehicles & Post-Verification Additions ────────────────────────
        print("4. Creating Vehicles & Post-Verification queue...")
        vehicles_data = [
            ("Imran Khan Logistics", "towing_truck", "LES-4512", "Hino Flatbed Tow Truck", 2022, "10 Ton", True, False, False),
            ("Imran Khan Logistics", "dumper", "LEA-8819", "Isuzu 6-Wheel Dumper", 2021, "16 CBM", True, False, False),
            ("Punjab Recovery & Towing", "towing_truck", "LXZ-1002", "Heavy Wheel-Lift Tow Truck", 2023, "15 Ton", True, True, False), # Post-verification addition!
            ("Punjab Recovery & Towing", "forklift", "KHI-3341", "Toyota 3-Ton Forklift", 2020, "3 Ton", True, False, False),
            ("Indus Heavy Excavators", "excavator", "MUL-5591", "CAT 320D Hydraulic Excavator", 2022, "22 Ton", True, False, False),
            ("Indus Heavy Excavators", "bulldozer", "FSD-7714", "Komatsu D65 Crawler Bulldozer", 2019, "20 Ton", False, True, False), # Post-verification addition!
            ("Lahore Industrial Cranes", "crane", "LHR-9921", "Tadano 50 Ton Mobile Crane", 2023, "50 Ton", True, False, False),
            ("Zubair Harvester Services", "harvester", "BWP-6612", "Claas Dominator Grain Harvester", 2021, "Standard", True, False, False),
            ("Bilal Sand Trolley Transport", "sand_trolley", "RWP-4411", "Tractor Double Trolley", 2022, "800 Cu Ft", True, False, False),
        ]

        vehicle_ids = []
        for prov_name, vtype, vnum, vmodel, vyear, cap, avail, post_verif, reviewed in vehicles_data:
            pid = provider_ids.get(prov_name)
            if not pid:
                continue
            vid = str(uuid.uuid4())
            session.run("""
            MATCH (p:Provider {id: $pid})
            MERGE (v:Vehicle {vehicleNumber: $vnum})
            ON CREATE SET
                v.id = $vid,
                v.vehicleType = $vtype,
                v.vehicleModel = $vmodel,
                v.vehicleYear = $vyear,
                v.capacity = $cap,
                v.isAvailable = $avail,
                v.isVerified = true,
                v.addedAfterVerification = $postVerif,
                v.adminReviewed = $reviewed,
                v.vehicleImageBase64 = $doc,
                v.vehicleLicenseImageBase64 = $doc,
                v.createdAt = datetime() - duration({days: 20})
            MERGE (p)-[:OWNS]->(v)
            """, {
                "pid": pid, "vid": vid, "vtype": vtype, "vnum": vnum,
                "vmodel": vmodel, "vyear": vyear, "cap": cap, "avail": avail,
                "postVerif": post_verif, "reviewed": reviewed, "doc": SAMPLE_DOC
            })
            vehicle_ids.append(vid)

        # ── 5. Seekers (Customers) ────────────────────────────────────────────
        print("5. Creating Seekers (Customers)...")
        seekers = [
            ("Ahmed Construction Co.", "ahmed.construction@pk.com", "+92 300 8881111", True),
            ("Fatima Builders Ltd.", "fatima.builders@gmail.com", "+92 321 7772222", True),
            ("Usman Farooq", "usman.farooq@outlook.com", "+92 333 6663333", True),
            ("Zainab Agri Farms", "zainab.farms@pk.com", "+92 313 5554444", True),
            ("Hassan Roadways Transport", "hassan.roadways@gmail.com", "+92 345 4445555", True),
            ("Old Stale Customer", "stale.customer@inactive.pk", "+92 300 9990000", False),
        ]
        seeker_ids = {}
        for name, email, phone, active in seekers:
            sid = str(uuid.uuid4())
            session.run("""
            MERGE (s:Seeker {email: $email})
            ON CREATE SET
                s.id = $sid,
                s.name = $name,
                s.phone = $phone,
                s.role = 'seeker',
                s.isActive = $active,
                s.createdAt = datetime() - duration({days: 80})
            """, {"sid": sid, "name": name, "email": email, "phone": phone, "active": active})
            rec = session.run("MATCH (s:Seeker {email: $email}) RETURN s.id AS id", {"email": email}).single()
            if rec:
                seeker_ids[name] = rec["id"]

        # ── 6. Services Catalogue ─────────────────────────────────────────────
        print("6. Creating Services Catalogue...")
        services_list = [
            ("Imran Khan Logistics", "Emergency Breakdown Towing", "towing", 5000, 250, 0, True),
            ("Imran Khan Logistics", "Heavy Earth & Gravel Haulage", "dumper", 8000, 300, 1500, True),
            ("Punjab Recovery & Towing", "24/7 Highway Recovery Towing", "towing", 6000, 280, 0, True),
            ("Punjab Recovery & Towing", "Warehouse Pallet Loading & Handling", "forklift", 4000, 0, 1800, True),
            ("Indus Heavy Excavators", "Deep Trenching & Basement Excavation", "excavator", 15000, 0, 4500, True),
            ("Indus Heavy Excavators", "Land Leveling & Site Clearing", "bulldozer", 18000, 0, 5000, True),
            ("Lahore Industrial Cranes", "50T Industrial Plant Crane Lifting", "crane", 25000, 0, 7500, True),
            ("Zubair Harvester Services", "Wheat & Rice Crop Harvesting", "harvester", 12000, 0, 3500, True),
            ("Bilal Sand Trolley Transport", "River Sand & Construction Trolley Supply", "sand_trolley", 4500, 150, 0, True),
            ("Imran Khan Logistics", "Legacy Towing Prototype", "towing", 3500, 150, 0, False), # Inactive
        ]
        for prov_name, sname, cat, base, per_km, per_hr, active in services_list:
            pid = provider_ids.get(prov_name)
            if not pid:
                continue
            sid = str(uuid.uuid4())
            session.run("""
            MATCH (p:Provider {id: $pid})
            MERGE (s:Service {name: $sname, providerId: $pid})
            ON CREATE SET
                s.id = $sid,
                s.category = $cat,
                s.basePrice = $base,
                s.pricePerKm = $perKm,
                s.pricePerHour = $perHr,
                s.isActive = $active,
                s.createdAt = datetime() - duration({days: 40})
            MERGE (p)-[:OFFERS]->(s)
            """, {
                "pid": pid, "sid": sid, "sname": sname, "cat": cat,
                "base": base, "perKm": per_km, "perHr": per_hr, "active": active
            })

        # ── 7. Bookings Across Statuses (Last 45 Days) ─────────────────────────
        print("7. Generating Bookings across timeline and statuses...")
        statuses = ["completed", "completed", "completed", "completed", "active", "in_progress", "provider_arriving", "pending", "cancelled", "rejected"]
        categories = ["crane", "towing_truck", "excavator", "bulldozer", "dumper", "forklift", "harvester", "sand_trolley"]

        seeker_names = list(seeker_ids.keys())
        prov_names = [k for k in provider_ids.keys() if k != "Inactive Provider Ltd"]

        addresses = [
            ("Gulberg III, Lahore", "Sundar Industrial Estate, Lahore", 35.4),
            ("DHA Phase 6, Lahore", "Motorway Toll Plaza M2, Lahore", 24.1),
            ("Ferozepur Road Industrial Zone", "Kala Shah Kaku Interchange", 48.6),
            ("Multan Road Near Thokar", "Raiwind Road Industrial Park", 18.2),
            ("Township Industrial Sector", "Quaid-e-Azam Industrial Estate", 12.8),
            ("Ring Road Northern Loop", "Badami Bagh Auto Market", 28.5),
        ]

        cancel_reasons = [
            "Customer rescheduled ground breaking due to rain",
            "Disputed additional waiting charges on arrival",
            "Alternative local equipment arranged before dispatch",
            "Site access road blocked by municipal construction",
        ]

        booking_ids_created = []

        # Create 40 realistic bookings distributed across last 35 days
        for i in range(40):
            bid = str(uuid.uuid4())
            b_status = statuses[i % len(statuses)]
            b_cat = categories[i % len(categories)]
            b_seeker_name = seeker_names[i % len(seeker_names)]
            b_prov_name = prov_names[i % len(prov_names)]
            b_seeker_id = seeker_ids[b_seeker_name]
            b_prov_id = provider_ids[b_prov_name]

            pickup, drop, dist = addresses[i % len(addresses)]
            days_ago = (i * 35) // 40  # Distributed over last 35 days
            hours_ago = random.randint(1, 23)

            est_price = random.randint(12, 85) * 1000
            final_price = est_price if b_status == "completed" else (est_price if b_status in ("active", "in_progress") else 0)

            cancellation_reason = cancel_reasons[i % len(cancel_reasons)] if b_status == "cancelled" else None

            # Label format: Booking and Booking:ServiceType
            label_suffix = "".join(w.title() for w in b_cat.split("_"))
            dynamic_label = f"Booking:{label_suffix}"

            cypher = f"""
            CREATE (b:Booking:{dynamic_label} {{
                id: $bid,
                seekerId: $seekerId,
                seekerName: $seekerName,
                providerId: $provId,
                providerName: $provName,
                serviceType: $serviceType,
                status: $status,
                pickupAddress: $pickup,
                dropAddress: $drop,
                distanceInKm: $dist,
                estimatedPrice: $estPrice,
                finalPrice: $finalPrice,
                cancellationReason: $cancelReason,
                scheduledDateTime: datetime() - duration({{days: $daysAgo, hours: $hoursAgo}}),
                createdAt: datetime() - duration({{days: $daysAgo, hours: $hoursAgo}}),
                updatedAt: datetime() - duration({{days: $daysAgo, hours: 1}})
            }})
            RETURN b.id AS id
            """
            session.run(cypher, {
                "bid": bid, "seekerId": b_seeker_id, "seekerName": b_seeker_name,
                "provId": b_prov_id, "provName": b_prov_name,
                "serviceType": b_cat, "status": b_status,
                "pickup": pickup, "drop": drop, "dist": dist,
                "estPrice": est_price, "finalPrice": final_price,
                "cancelReason": cancellation_reason,
                "daysAgo": days_ago, "hoursAgo": hours_ago
            })
            booking_ids_created.append((bid, b_prov_id, b_seeker_id, b_status))

        # ── 8. Reviews & Feedback (Positive and Low-Rated Complaints) ─────────
        print("8. Generating Reviews, Ratings, and Low-Rated Complaints...")
        feedback_samples = [
            # High ratings
            (5, "Exceptional crane precision. Handled the steel trusses on our industrial shed flawlessly.", "seeker"),
            (5, "Arrived in 20 minutes with a modern flatbed. Best towing experience in Lahore.", "seeker"),
            (4, "Excavation completed on schedule. Minor delay on diesel refuel but great operator.", "seeker"),
            (4, "Harvester worked clean with minimum grain loss. Highly recommended.", "seeker"),
            # Low ratings (<= 2 stars for Complaints testing!)
            (1, "Crane hydraulic cylinder leaked on site. Operator took 5 hours to fix and charged extra.", "seeker"),
            (2, "Towing driver argued about highway toll charges and demanded direct cash. Unprofessional.", "seeker"),
            (1, "Bulldozer arrived 3 hours late and operator damaged our perimeter boundary wall.", "seeker"),
            (2, "Dumper truck was half-filled compared to the cubic capacity quoted in the booking.", "seeker"),
        ]

        for idx, (rating, comment, rtype) in enumerate(feedback_samples):
            fid = str(uuid.uuid4())
            b_info = booking_ids_created[idx % len(booking_ids_created)]
            session.run("""
            CREATE (f:Feedback {
                id: $fid,
                bookingId: $bid,
                providerId: $pid,
                seekerId: $sid,
                rating: $rating,
                comment: $comment,
                reviewerType: $rtype,
                createdAt: datetime() - duration({days: $daysAgo})
            })
            """, {
                "fid": fid, "bid": b_info[0], "pid": b_info[1], "sid": b_info[2],
                "rating": rating, "comment": comment, "rtype": rtype,
                "daysAgo": idx * 3
            })

        # ── 9. Notifications Log ──────────────────────────────────────────────
        print("9. Generating In-App Notifications log...")
        notif_templates = [
            ("Booking Confirmed", "Your booking for 50T Mobile Crane has been accepted.", "booking_update", False),
            ("Operator En Route", "Driver Imran Khan is 12 mins away from pickup.", "booking_update", True),
            ("Payment Settled", "Payment of PKR 45,000 received successfully.", "payment", True),
            ("Fleet Maintenance Alert", "Scheduled diagnostic check required for Towing Truck LES-4512.", "system", False),
            ("Spring Industrial Promo", "Enjoy 15% discount on all weekend harvester & crane rentals.", "promo", True),
            ("Booking Cancelled", "Booking #BK-8891 cancelled: Road access obstructed.", "booking_update", True),
        ]

        first_seeker_id = list(seeker_ids.values())[0]
        for idx, (title, body, ntype, is_read) in enumerate(notif_templates):
            nid = str(uuid.uuid4())
            session.run("""
            CREATE (n:Notification {
                id: $nid,
                userId: $uid,
                title: $title,
                body: $body,
                type: $ntype,
                isRead: $isRead,
                createdAt: datetime() - duration({days: $daysAgo, hours: 3})
            })
            """, {
                "nid": nid, "uid": first_seeker_id, "title": title,
                "body": body, "ntype": ntype, "isRead": is_read,
                "daysAgo": idx * 2
            })

    print("Comprehensive database seeding finished successfully!")


if __name__ == "__main__":
    seed_all()
