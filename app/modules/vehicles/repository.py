from typing import Optional, Dict, Any
from datetime import datetime
import uuid
from app.core.database.neo4j_driver import neo4j_driver


class Vehicle:
    """Vehicle model for service providers"""
    
    def __init__(
        self,
        id: str,
        provider_id: str,
        vehicle_type: str,
        vehicle_number: str,
        vehicle_model: Optional[str] = None,
        vehicle_year: Optional[str] = None,
        vehicle_image_url: Optional[str] = None,
        vehicle_image_base64: Optional[str] = None,
        is_available: bool = True,
        capacity: Optional[float] = None,
        created_at: Optional[datetime] = None,
        updated_at: Optional[datetime] = None,
    ):
        self.id = id
        self.provider_id = provider_id
        self.vehicle_type = vehicle_type
        self.vehicle_number = vehicle_number
        self.vehicle_model = vehicle_model
        self.vehicle_year = vehicle_year
        self.vehicle_image_url = vehicle_image_url
        self.vehicle_image_base64 = vehicle_image_base64
        self.is_available = is_available
        self.capacity = capacity
        self.created_at = created_at or datetime.now()
        self.updated_at = updated_at or datetime.now()
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'Vehicle':
        """Create Vehicle instance from dictionary (handles both snake_case and camelCase)"""
        from neo4j.time import DateTime
        
        # Helper to convert Neo4j DateTime
        def parse_datetime(val):
            if val is None:
                return None
            if isinstance(val, DateTime):
                return datetime(val.year, val.month, val.day, val.hour, val.minute, int(val.second))
            if isinstance(val, datetime):
                return val
            if isinstance(val, str):
                return datetime.fromisoformat(val.replace('Z', '+00:00'))
            return None
        
        return cls(
            id=data.get('id', str(uuid.uuid4())),
            provider_id=data.get('providerId') or data.get('provider_id', ''),
            vehicle_type=data.get('vehicleType') or data.get('vehicle_type', ''),
            vehicle_number=data.get('vehicleNumber') or data.get('vehicle_number') or data.get('licensePlate', ''),
            vehicle_model=data.get('vehicleModel') or data.get('vehicle_model'),
            vehicle_year=data.get('vehicleYear') or data.get('vehicle_year'),
            vehicle_image_url=data.get('vehicleImageUrl') or data.get('vehicle_image_url'),
            vehicle_image_base64=data.get('vehicleImageBase64') or data.get('vehicle_image_base64'),
            is_available=data.get('isAvailable', data.get('is_available', True)),
            capacity=data.get('capacity'),
            created_at=parse_datetime(data.get('createdAt') or data.get('created_at')),
            updated_at=parse_datetime(data.get('updatedAt') or data.get('updated_at')),
        )
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert Vehicle to dictionary"""
        return {
            'id': self.id,
            'provider_id': self.provider_id,
            'vehicle_type': self.vehicle_type,
            'vehicle_number': self.vehicle_number,
            'vehicle_model': self.vehicle_model,
            'vehicle_year': self.vehicle_year,
            'vehicle_image_url': self.vehicle_image_url,
            'vehicle_image_base64': self.vehicle_image_base64,
            'is_available': self.is_available,
            'capacity': self.capacity,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'updated_at': self.updated_at.isoformat() if self.updated_at else None,
        }
    
    def to_neo4j_props(self) -> Dict[str, Any]:
        """Convert Vehicle to Neo4j properties"""
        props = self.to_dict()
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
    def create(vehicle_data: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Create a new vehicle in the database and link to provider"""
        # Ensure isAvailable defaults to true
        if 'isAvailable' not in vehicle_data:
            vehicle_data['isAvailable'] = True
        
        # Handle parameter name variations
        vehicle_data['vehicleNumberParam'] = vehicle_data.get('vehicleNumber') or vehicle_data.get('licensePlate', '')
        vehicle_data['vehicleImageBase64'] = vehicle_data.get('vehicleImageBase64') or vehicle_data.get('vehicleImageUrl') or ''
        vehicle_data['vehicleLicenseImageBase64Param'] = vehicle_data.get('vehicleLicenseImageBase64') or None
        vehicle_data['capacityParam'] = vehicle_data.get('capacity') or 0.0
        vehicle_data['extraFieldsParam'] = vehicle_data.get('extraFields') or None
        vehicle_data['isVerified'] = bool(vehicle_data.get('isVerified', False))
        vehicle_data['addedAfterVerification'] = bool(vehicle_data.get('addedAfterVerification', False))

        query = """
        MATCH (p)
        WHERE (p:Provider OR p:User OR p:Seeker) AND p.id = $providerId
        CREATE (v:Vehicle {
            id: randomUUID(),
            providerId: $providerId,
            vehicleType: $vehicleType,
            vehicleNumber: $vehicleNumberParam,
            vehicleModel: $vehicleModel,
            vehicleYear: $vehicleYear,
            vehicleImageBase64: $vehicleImageBase64,
            vehicleLicenseImageBase64: $vehicleLicenseImageBase64Param,
            capacity: $capacityParam,
            extraFields: $extraFieldsParam,
            isAvailable: $isAvailable,
            isVerified: $isVerified,
            addedAfterVerification: $addedAfterVerification,
            createdAt: datetime(),
            updatedAt: datetime()
        })
        CREATE (p)-[:OWNS]->(v)
        RETURN v
        """
        
        result = neo4j_driver.execute_write(query, vehicle_data)
        if result and result[0]['v']:
            return Vehicle._serialize_neo4j_data(result[0]['v'])
        return None
    
    @staticmethod
    def update(vehicle_id: str, update_data: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Update vehicle with dynamic fields"""
        # Build dynamic SET clause
        set_clauses = []
        params = {"vehicleId": vehicle_id}
        
        field_mapping = {
            'vehicleModel': 'vehicleModel',
            'vehicleYear': 'vehicleYear',
            'licensePlate': 'vehicleNumber',
            'vehicleNumber': 'vehicleNumber',
            'capacity': 'capacity',
            'pricePerHour': 'pricePerHour',
            'pricePerKm': 'pricePerKm',
            'vehicleImageUrl': 'vehicleImageUrl',
            'vehicleImageBase64': 'vehicleImageBase64',
            'vehicleLicenseImageBase64': 'vehicleLicenseImageBase64',
            'imageUrls': 'vehicleImageUrl',
            'isAvailable': 'isAvailable',
            'extraFields': 'extraFields',
        }
        
        for key, neo4j_key in field_mapping.items():
            if key in update_data and update_data[key] is not None:
                # Handle imageUrls array - take first item
                if key == 'imageUrls' and isinstance(update_data[key], list):
                    if update_data[key]:
                        set_clauses.append(f"v.{neo4j_key} = ${key}")
                        params[key] = update_data[key][0]
                else:
                    set_clauses.append(f"v.{neo4j_key} = ${key}")
                    params[key] = update_data[key]
        
        set_clauses.append("v.updatedAt = datetime()")
        
        if not set_clauses:
            return None
        
        query = f"""
        MATCH (v:Vehicle {{id: $vehicleId}})
        SET {", ".join(set_clauses)}
        RETURN v
        """
        
        result = neo4j_driver.execute_write(query, params)
        if result and result[0]['v']:
            return Vehicle._serialize_neo4j_data(result[0]['v'])
        return None
    
    @staticmethod
    def get_all_for_admin() -> list:
        """Return all vehicles with provider info — for admin monitoring panel."""
        query = """
        MATCH (v:Vehicle)
        OPTIONAL MATCH (p)-[:OWNS]->(v)
        WHERE p:Provider OR p:User OR p:Seeker
        RETURN v,
               p.id   AS providerId,
               p.name AS providerName,
               coalesce(p.isVerified, false) AS providerIsVerified
        ORDER BY v.createdAt DESC
        """
        result = neo4j_driver.execute_read(query, {})
        vehicles = []
        if result:
            for record in result:
                if record['v']:
                    v = Vehicle._serialize_neo4j_data(record['v'])
                    v['providerName'] = record.get('providerName')
                    v['providerIsVerified'] = record.get('providerIsVerified', False)
                    vehicles.append(v)
        return vehicles

    @staticmethod
    def delete(vehicle_id: str) -> bool:
        """Delete a vehicle from the database"""
        # Use RETURN 1 instead of count(v) — after DETACH DELETE the node is
        # out of scope and count(v) always returns 0, causing a false 404.
        # When MATCH finds nothing, no rows are returned so result is [].
        query = """
        MATCH (v:Vehicle {id: $vehicleId})
        DETACH DELETE v
        RETURN 1 as deleted
        """

        params = {"vehicleId": vehicle_id}
        result = neo4j_driver.execute_write(query, params)

        return bool(result)
