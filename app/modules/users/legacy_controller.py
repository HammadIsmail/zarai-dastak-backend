from typing import List, Optional, Dict, Any
from datetime import datetime
from app.core.database import get_neo4j_driver
from app.modules.users.repository import User


class UserController:
    """Controller for User operations (MVC Pattern)"""
    
    def __init__(self):
        self.db = get_neo4j_driver()
    
    def create_user(self, user_data: Dict[str, Any]) -> User:
        """Create a new user in Neo4j with role-based label (Seeker/Provider)"""
        user = User.from_dict(user_data)
        
        # Determine node label based on role
        role = user.role.lower() if user.role else 'seeker'
        node_label = 'Provider' if role == 'provider' else 'Seeker'
        
        query = f"""
        CREATE (u:{node_label} {{
            id: $id,
            email: $email,
            name: $name,
            phone: $phone,
            role: $role,
            profile_image_url: $profile_image_url,
            is_verified: $is_verified,
            is_active: $is_active,
            cnic: $cnic,
            driving_license: $driving_license,
            rating: $rating,
            completed_bookings: $completed_bookings,
            latitude: $latitude,
            longitude: $longitude,
            address: $address,
            created_at: datetime($created_at),
            updated_at: datetime($updated_at)
        }})
        RETURN u
        """
        
        self.db.execute_write(query, user.to_neo4j_props())
        return user
    
    def get_user_by_id(self, user_id: str) -> Optional[User]:
        """Get user by ID (works with Seeker, Provider, or legacy User labels)"""
        query = """
        MATCH (u {id: $user_id})
        WHERE u:Seeker OR u:Provider OR u:User
        RETURN u
        """
        
        result = self.db.execute_read(query, {'user_id': user_id})
        
        if result and len(result) > 0:
            user_data = result[0]['u']
            return User.from_dict(user_data)
        return None
    
    def get_user_by_email(self, email: str) -> Optional[User]:
        """Get user by email (works with Seeker, Provider, or legacy User labels)"""
        query = """
        MATCH (u {email: $email})
        WHERE u:Seeker OR u:Provider OR u:User
        RETURN u
        """
        
        result = self.db.execute_read(query, {'email': email})
        
        if result and len(result) > 0:
            user_data = result[0]['u']
            return User.from_dict(user_data)
        return None
    
    def update_user(self, user_id: str, updates: Dict[str, Any]) -> Optional[User]:
        """Update user information"""
        updates['updated_at'] = datetime.now().isoformat()
        
        set_clause = ', '.join([f'u.{key} = ${key}' for key in updates.keys()])
        
        query = f"""
        MATCH (u {{id: $user_id}})
        WHERE u:Seeker OR u:Provider OR u:User
        SET {set_clause}
        RETURN u
        """
        
        params = {'user_id': user_id, **updates}
        result = self.db.execute_write(query, params)
        
        if result and len(result) > 0:
            user_data = result[0]['u']
            return User.from_dict(user_data)
        return None
    
    def get_providers_by_service_type(self, service_type: str) -> List[User]:
        """Get all providers offering a specific service type"""
        query = """
        MATCH (u:Provider {is_active: true, is_verified: true})
        -[:OWNS]->(v:Vehicle {vehicle_type: $service_type, is_available: true})
        RETURN DISTINCT u
        """
        
        result = self.db.execute_read(query, {'service_type': service_type})
        return [User.from_dict(record['u']) for record in result]
    
    def update_provider_rating(self, provider_id: str, new_rating: float):
        """Update provider's average rating"""
        query = """
        MATCH (u:Provider {id: $provider_id})
        SET u.rating = $new_rating,
            u.updated_at = datetime()
        RETURN u
        """
        
        self.db.execute_write(query, {
            'provider_id': provider_id,
            'new_rating': new_rating
        })
    
    def increment_completed_bookings(self, provider_id: str):
        """Increment completed bookings count"""
        query = """
        MATCH (u:Provider {id: $provider_id})
        SET u.completedBookings = coalesce(u.completedBookings, 0) + 1,
            u.updatedAt = datetime()
        RETURN u
        """
        
        self.db.execute_write(query, {'provider_id': provider_id})
    
    def delete_user(self, user_id: str) -> bool:
        """Delete user (soft delete by marking inactive)"""
        query = """
        MATCH (u {id: $user_id})
        WHERE u:Seeker OR u:Provider OR u:User
        SET u.is_active = false,
            u.updated_at = datetime()
        RETURN u
        """
        
        result = self.db.execute_write(query, {'user_id': user_id})
        return len(result) > 0
