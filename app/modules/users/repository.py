from typing import Optional, Dict, Any, List
from datetime import datetime
import uuid
from app.core.database.neo4j_driver import neo4j_driver


class User:
    """User model for both service seekers and providers"""
    
    def __init__(
        self,
        id: str,
        email: str,
        name: str,
        phone: str,
        role: str,  # 'seeker' or 'provider'
        profile_image_url: Optional[str] = None,
        is_verified: bool = False,
        is_active: bool = True,
        cnic: Optional[str] = None,
        driving_license: Optional[str] = None,
        rating: Optional[float] = None,
        completed_bookings: int = 0,
        latitude: Optional[float] = None,
        longitude: Optional[float] = None,
        address: Optional[str] = None,
        created_at: Optional[datetime] = None,
        updated_at: Optional[datetime] = None,
    ):
        self.id = id
        self.email = email
        self.name = name
        self.phone = phone
        self.role = role
        self.profile_image_url = profile_image_url
        self.is_verified = is_verified
        self.is_active = is_active
        self.cnic = cnic
        self.driving_license = driving_license
        self.rating = rating
        self.completed_bookings = completed_bookings
        self.latitude = latitude
        self.longitude = longitude
        self.address = address
        self.created_at = created_at or datetime.now()
        self.updated_at = updated_at or datetime.now()
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'User':
        """Create User instance from dictionary"""
        return cls(
            id=data.get('id', str(uuid.uuid4())),
            email=data['email'],
            name=data['name'],
            phone=data['phone'],
            role=data['role'],
            profile_image_url=data.get('profile_image_url'),
            is_verified=data.get('is_verified', False),
            is_active=data.get('is_active', True),
            cnic=data.get('cnic'),
            driving_license=data.get('driving_license'),
            rating=data.get('rating'),
            completed_bookings=data.get('completed_bookings', 0),
            latitude=data.get('latitude'),
            longitude=data.get('longitude'),
            address=data.get('address'),
            created_at=data.get('created_at'),
            updated_at=data.get('updated_at'),
        )
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert User to dictionary"""
        return {
            'id': self.id,
            'email': self.email,
            'name': self.name,
            'phone': self.phone,
            'role': self.role,
            'profile_image_url': self.profile_image_url,
            'is_verified': self.is_verified,
            'is_active': self.is_active,
            'cnic': self.cnic,
            'driving_license': self.driving_license,
            'rating': self.rating,
            'completed_bookings': self.completed_bookings,
            'latitude': self.latitude,
            'longitude': self.longitude,
            'address': self.address,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'updated_at': self.updated_at.isoformat() if self.updated_at else None,
        }
    
    def to_neo4j_props(self) -> Dict[str, Any]:
        """Convert User to Neo4j properties"""
        props = self.to_dict()
        # Convert datetime to ISO string for Neo4j
        if props['created_at']:
            props['created_at'] = self.created_at.isoformat()
        if props['updated_at']:
            props['updated_at'] = self.updated_at.isoformat()
        return props
    
    # Database Operations (Model Layer)
    
    @staticmethod
    def _serialize_neo4j_data(data: Dict[str, Any]) -> Dict[str, Any]:
        """Convert Neo4j data types to Python types for GraphQL"""
        from neo4j.time import DateTime as Neo4jDateTime
        
        serialized = {}
        for key, value in data.items():
            if isinstance(value, Neo4jDateTime):
                # Convert Neo4j DateTime to Python datetime for GraphQL
                serialized[key] = value.to_native()
            elif value is None:
                serialized[key] = None
            else:
                serialized[key] = value
        return serialized
    
    @staticmethod
    def create(user_data: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Create a new user in Neo4j (synced from Firebase) with role-based label"""
        # Determine node label based on role
        role = user_data.get('role', 'seeker').lower() if user_data.get('role') else 'seeker'
        node_label = 'Provider' if role == 'provider' else 'Seeker'
        
        # Use dynamic label based on role
        query = f"""
        MERGE (u:{node_label} {{id: $firebaseUid}})
        ON CREATE SET
            u.email = $email,
            u.name = $name,
            u.phone = $phone,
            u.role = $role,
            u.profileImageUrl = $profileImageUrl,
            u.cnic = $cnic,
            u.cnicFrontImageBase64 = $cnicFrontImageBase64,
            u.cnicBackImageBase64 = $cnicBackImageBase64,
            u.licenseImageBase64 = $licenseImageBase64,
            u.cnicFrontImageUrl = $cnicFrontImageUrl,
            u.cnicBackImageUrl = $cnicBackImageUrl,
            u.licenseImageUrl = $licenseImageUrl,
            u.vehicleImageUrl = $vehicleImageUrl,
            u.isVerified = $isVerified,
            u.isActive = $isActive,
            u.interests = $interests,
            u.latitude = $latitude,
            u.longitude = $longitude,
            u.rating = 0.0,
            u.completedBookings = 0,
            u.createdAt = datetime(),
            u.updatedAt = datetime()
        ON MATCH SET
            u.email = $email,
            u.name = $name,
            u.phone = $phone,
            u.profileImageUrl = $profileImageUrl,
            u.cnic = COALESCE($cnic, u.cnic),
            u.cnicFrontImageBase64 = COALESCE($cnicFrontImageBase64, u.cnicFrontImageBase64),
            u.cnicBackImageBase64 = COALESCE($cnicBackImageBase64, u.cnicBackImageBase64),
            u.licenseImageBase64 = COALESCE($licenseImageBase64, u.licenseImageBase64),
            u.cnicFrontImageUrl = COALESCE($cnicFrontImageUrl, u.cnicFrontImageUrl),
            u.cnicBackImageUrl = COALESCE($cnicBackImageUrl, u.cnicBackImageUrl),
            u.licenseImageUrl = COALESCE($licenseImageUrl, u.licenseImageUrl),
            u.vehicleImageUrl = COALESCE($vehicleImageUrl, u.vehicleImageUrl),
            u.isVerified = $isVerified,
            u.isActive = $isActive,
            u.interests = COALESCE($interests, u.interests),
            u.latitude = COALESCE($latitude, u.latitude),
            u.longitude = COALESCE($longitude, u.longitude),
            u.updatedAt = datetime()
        RETURN u
        """

        # Ensure optional fields have default values
        user_data.setdefault('profileImageUrl', None)
        user_data.setdefault('cnic', None)
        user_data.setdefault('cnicFrontImageBase64', None)
        user_data.setdefault('cnicBackImageBase64', None)
        user_data.setdefault('licenseImageBase64', None)
        user_data.setdefault('cnicFrontImageUrl', None)
        user_data.setdefault('cnicBackImageUrl', None)
        user_data.setdefault('licenseImageUrl', None)
        user_data.setdefault('vehicleImageUrl', None)
        user_data.setdefault('interests', [])
        user_data.setdefault('latitude', None)
        user_data.setdefault('longitude', None)
        
        result = neo4j_driver.execute_write(query, user_data)
        
        if result and len(result) > 0:
            user_node = result[0].get('u') if hasattr(result[0], 'get') else result[0]['u']
            if user_node:
                return User._serialize_neo4j_data(dict(user_node))
        
        return None
    
    @staticmethod
    def get_by_id(user_id: str) -> Optional[Dict[str, Any]]:
        """Get user by Firebase UID from Neo4j (works with Seeker, Provider, or legacy User labels)"""
        query = """
        MATCH (u {id: $userId})
        WHERE u:Seeker OR u:Provider OR u:User
        OPTIONAL MATCH (b)
        WHERE any(label IN labels(b) WHERE label STARTS WITH 'Booking')
          AND b.providerId = $userId
          AND b.status = 'completed'
        RETURN u, count(b) AS completedBookingsCount
        """

        result = neo4j_driver.execute_read(query, {"userId": user_id})

        if result and len(result) > 0:
            row = result[0]
            user_node = row.get('u') if hasattr(row, 'get') else row['u']
            if user_node:
                data = User._serialize_neo4j_data(dict(user_node))
                count = row.get('completedBookingsCount') if hasattr(row, 'get') else row['completedBookingsCount']
                data['completedBookings'] = int(count) if count is not None else 0
                return data

        return None
    
    @staticmethod
    def get_by_email(email: str) -> Optional[Dict[str, Any]]:
        """Get user by email from Neo4j (works with Seeker, Provider, or legacy User labels)"""
        query = """
        MATCH (u {email: $email})
        WHERE u:Seeker OR u:Provider OR u:User
        RETURN u
        """
        
        result = neo4j_driver.execute_read(query, {"email": email})
        
        if result and len(result) > 0:
            user_node = result[0].get('u') if hasattr(result[0], 'get') else result[0]['u']
            if user_node:
                return User._serialize_neo4j_data(dict(user_node))
        
        return None

    @staticmethod
    def get_by_phone(phone: str) -> Optional[Dict[str, Any]]:
        """Get user by phone from Neo4j (works with Seeker, Provider, or legacy User labels)"""
        query = """
        MATCH (u {phone: $phone})
        WHERE u:Seeker OR u:Provider OR u:User
        RETURN u
        """

        result = neo4j_driver.execute_read(query, {"phone": phone})

        if result and len(result) > 0:
            user_node = result[0].get('u') if hasattr(result[0], 'get') else result[0]['u']
            if user_node:
                return User._serialize_neo4j_data(dict(user_node))

        return None

    @staticmethod
    def get_by_cnic(cnic: str) -> Optional[Dict[str, Any]]:
        """Get provider by CNIC from Neo4j"""
        query = """
        MATCH (u {cnic: $cnic})
        WHERE u:Provider OR u:User
        RETURN u
        """

        result = neo4j_driver.execute_read(query, {"cnic": cnic})

        if result and len(result) > 0:
            user_node = result[0].get('u') if hasattr(result[0], 'get') else result[0]['u']
            if user_node:
                return User._serialize_neo4j_data(dict(user_node))

        return None
    
    @staticmethod
    def update(user_id: str, update_data: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Update user information in Neo4j"""
        # Build dynamic SET clause
        set_clauses = []
        params = {"userId": user_id}
        
        field_mapping = {
            'name': 'name',
            'phone': 'phone',
            'profileImageUrl': 'profileImageUrl',
            'cnic': 'cnic',
            'drivingLicense': 'drivingLicense',
            'latitude': 'latitude',
            'longitude': 'longitude',
            'address': 'address',
            'isActive': 'isActive',
            'isVerified': 'isVerified',
            'fcmToken': 'fcmToken'
        }
        
        for key, neo4j_key in field_mapping.items():
            if key in update_data and update_data[key] is not None:
                set_clauses.append(f"u.{neo4j_key} = ${key}")
                params[key] = update_data[key]
        
        if not set_clauses:
            # No fields to update
            return User.get_by_id(user_id)
        
        set_clauses.append("u.updatedAt = datetime()")
        
        query = f"""
        MATCH (u {{id: $userId}})
        WHERE u:Seeker OR u:Provider OR u:User
        SET {", ".join(set_clauses)}
        RETURN u
        """
        
        result = neo4j_driver.execute_write(query, params)
        if result and result[0]['u']:
            return User._serialize_neo4j_data(result[0]['u'])
        return None

    @staticmethod
    def update_interests(user_id: str, interests: list) -> Optional[Dict[str, Any]]:
        """Replace a seeker's interest list."""
        query = """
        MATCH (u:Seeker {id: $userId})
        SET u.interests = $interests, u.updatedAt = datetime()
        RETURN u
        """
        result = neo4j_driver.execute_write(query, {'userId': user_id, 'interests': interests})
        if result and result[0]['u']:
            return User._serialize_neo4j_data(dict(result[0]['u']))
        return None

    @staticmethod
    def get_interests(user_id: str) -> list:
        """Return a seeker's stored interests list (empty list if none)."""
        query = """
        MATCH (u:Seeker {id: $userId})
        RETURN coalesce(u.interests, []) AS interests
        """
        result = neo4j_driver.execute_read(query, {'userId': user_id})
        if result:
            return result[0].get('interests') or []
        return []

    @staticmethod
    def get_seekers_by_interest(category: str) -> List[Dict[str, Any]]:
        """Return all active Seekers that have $category in their interests and have an FCM token."""
        query = """
        MATCH (u:Seeker)
        WHERE $category IN coalesce(u.interests, [])
          AND u.isActive = true
          AND u.fcmToken IS NOT NULL
        RETURN u.id AS id, u.name AS name, u.fcmToken AS fcmToken
        """
        result = neo4j_driver.execute_read(query, {'category': category})
        return [dict(r) for r in result] if result else []
