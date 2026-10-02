from typing import List, Optional, Dict, Any
from datetime import datetime
from app.core.database import get_neo4j_driver
from app.modules.vehicles.repository import Vehicle


class VehicleController:
    """Controller for Vehicle operations (MVC Pattern)"""
    
    def __init__(self):
        self.db = get_neo4j_driver()
    
    def create_vehicle(self, vehicle_data: Dict[str, Any]) -> Vehicle:
        """Create a new vehicle and link to provider"""
        vehicle = Vehicle.from_dict(vehicle_data)
        
        query = """
        MATCH (p:User {id: $provider_id, role: 'provider'})
        CREATE (v:Vehicle {
            id: $id,
            provider_id: $provider_id,
            vehicle_type: $vehicle_type,
            vehicle_number: $vehicle_number,
            vehicle_model: $vehicle_model,
            vehicle_year: $vehicle_year,
            vehicle_image_url: $vehicle_image_url,
            is_available: $is_available,
            capacity: $capacity,
            created_at: datetime($created_at),
            updated_at: datetime($updated_at)
        })
        CREATE (p)-[:OWNS]->(v)
        RETURN v
        """
        
        self.db.execute_write(query, vehicle.to_neo4j_props())
        return vehicle
    
    def get_vehicle_by_id(self, vehicle_id: str) -> Optional[Vehicle]:
        """Get vehicle by ID"""
        query = """
        MATCH (v:Vehicle {id: $vehicle_id})
        RETURN v
        """
        
        result = self.db.execute_read(query, {'vehicle_id': vehicle_id})
        
        if result and len(result) > 0:
            vehicle_data = result[0]['v']
            return Vehicle.from_dict(vehicle_data)
        return None
    
    def get_provider_vehicles(self, provider_id: str) -> List[Vehicle]:
        """Get all vehicles owned by a provider"""
        query = """
        MATCH (v:Vehicle {providerId: $provider_id})
        RETURN v
        ORDER BY v.createdAt DESC
        """
        
        result = self.db.execute_read(query, {'provider_id': provider_id})
        return [Vehicle.from_dict(record['v']) for record in result]
    
    def get_available_vehicles(self, service_type: str) -> List[Vehicle]:
        """Get all available vehicles for a specific service type"""
        query = """
        MATCH (v:Vehicle {
            vehicleType: $service_type,
            isAvailable: true
        })
        OPTIONAL MATCH (p:User)-[:OWNS]->(v)
        WHERE p IS NULL OR (p.is_active = true AND p.is_verified = true)
        RETURN v
        ORDER BY v.createdAt DESC
        """
        
        result = self.db.execute_read(query, {'service_type': service_type})
        return [Vehicle.from_dict(record['v']) for record in result]
    
    def update_vehicle(self, vehicle_id: str, updates: Dict[str, Any]) -> Optional[Vehicle]:
        """Update vehicle information"""
        updates['updated_at'] = datetime.now().isoformat()
        
        set_clause = ', '.join([f'v.{key} = ${key}' for key in updates.keys()])
        
        query = f"""
        MATCH (v:Vehicle {{id: $vehicle_id}})
        SET {set_clause}
        RETURN v
        """
        
        params = {'vehicle_id': vehicle_id, **updates}
        result = self.db.execute_write(query, params)
        
        if result and len(result) > 0:
            vehicle_data = result[0]['v']
            return Vehicle.from_dict(vehicle_data)
        return None
    
    def set_vehicle_availability(self, vehicle_id: str, is_available: bool) -> bool:
        """Set vehicle availability status"""
        query = """
        MATCH (v:Vehicle {id: $vehicle_id})
        SET v.is_available = $is_available,
            v.updated_at = datetime()
        RETURN v
        """
        
        result = self.db.execute_write(query, {
            'vehicle_id': vehicle_id,
            'is_available': is_available
        })
        return len(result) > 0
    
    def delete_vehicle(self, vehicle_id: str) -> bool:
        """Delete vehicle"""
        query = """
        MATCH (v:Vehicle {id: $vehicle_id})
        DETACH DELETE v
        """
        
        self.db.execute_write(query, {'vehicle_id': vehicle_id})
        return True
