"""
Service Model - Represents services offered by providers
Clean, minimal model for service management
"""

from typing import Optional, Dict, Any, List
from datetime import datetime
from math import radians, sin, cos, sqrt, atan2
from app.core.database.neo4j_driver import neo4j_driver


def _haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Return great-circle distance in km between two lat/lng points."""
    R = 6371.0
    dlat = radians(lat2 - lat1)
    dlon = radians(lon2 - lon1)
    a = sin(dlat / 2) ** 2 + cos(radians(lat1)) * cos(radians(lat2)) * sin(dlon / 2) ** 2
    return R * 2 * atan2(sqrt(a), sqrt(1 - a))


class Service:
    """Service model - represents services offered by providers via vehicles"""
    
    def __init__(
        self,
        id: str,
        provider_id: str,
        vehicle_id: str,
        name: str,
        description: Optional[str] = None,
        base_price: float = 0.0,
        price_per_km: float = 0.0,
        price_per_hour: float = 0.0,
        category: str = "general",
        is_active: bool = True,
        created_at: Optional[datetime] = None,
        updated_at: Optional[datetime] = None,
    ):
        self.id = id
        self.provider_id = provider_id
        self.vehicle_id = vehicle_id
        self.name = name
        self.description = description
        self.base_price = base_price
        self.price_per_km = price_per_km
        self.price_per_hour = price_per_hour
        self.category = category
        self.is_active = is_active
        self.created_at = created_at or datetime.now()
        self.updated_at = updated_at or datetime.now()
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary"""
        return {
            'id': self.id,
            'providerId': self.provider_id,
            'vehicleId': self.vehicle_id,
            'name': self.name,
            'description': self.description,
            'imageUrl': getattr(self, 'image_url', None),
            'basePrice': self.base_price,
            'pricePerKm': self.price_per_km,
            'pricePerHour': self.price_per_hour,
            'category': self.category,
            'isActive': self.is_active,
            'createdAt': self.created_at.isoformat() if self.created_at else None,
            'updatedAt': self.updated_at.isoformat() if self.updated_at else None,
        }
    
    @staticmethod
    def _serialize_neo4j_data(data: Dict[str, Any]) -> Dict[str, Any]:
        """Convert Neo4j data types to Python types for GraphQL"""
        from neo4j.time import DateTime as Neo4jDateTime
        
        serialized = {}
        for key, value in data.items():
            if isinstance(value, Neo4jDateTime):
                # Convert Neo4j DateTime to Python datetime for GraphQL
                serialized[key] = value.to_native()
            elif isinstance(value, str) and 'T' in value and ('+' in value or 'Z' in value):
                # Handle ISO format strings with timezone
                try:
                    # Remove nanoseconds if present (keep only microseconds)
                    clean_value = value
                    if '.' in value:
                        parts = value.split('.')
                        if len(parts) == 2:
                            # Extract timezone
                            tz_part = ''
                            frac_part = parts[1]
                            for tz_char in ['+', '-', 'Z']:
                                if tz_char in frac_part:
                                    idx = frac_part.index(tz_char)
                                    tz_part = frac_part[idx:]
                                    frac_part = frac_part[:idx]
                                    break
                            # Truncate to 6 digits (microseconds)
                            frac_part = frac_part[:6].ljust(6, '0')
                            clean_value = f"{parts[0]}.{frac_part}{tz_part}"
                    serialized[key] = clean_value
                except:
                    serialized[key] = value
            elif value is None:
                serialized[key] = None
            else:
                serialized[key] = value
        return serialized
    
    # Database Operations
    
    @staticmethod
    def create(service_data: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Create a new service"""
        query = """
        MATCH (p)
        WHERE (p:Provider OR p:User OR p:Seeker) AND p.id = $providerId
        MATCH (v:Vehicle {id: $vehicleId})
        CREATE (s:Service {
            id: randomUUID(),
            providerId: $providerId,
            vehicleId: $vehicleId,
            name: $name,
            description: $description,
            imageUrl: $imageUrl,
            basePrice: $basePrice,
            pricePerKm: $pricePerKm,
            pricePerHour: $pricePerHour,
            category: $category,
            extraFields: $extraFields,
            serviceBaseLatitude: $serviceBaseLatitude,
            serviceBaseLongitude: $serviceBaseLongitude,
            serviceBaseAddress: $serviceBaseAddress,
            isActive: true,
            createdAt: datetime(),
            updatedAt: datetime()
        })
        CREATE (p)-[:OFFERS]->(s)
        CREATE (v)-[:PROVIDES]->(s)
        RETURN s
        """
        
        params = {
            'providerId': service_data.get('providerId'),
            'vehicleId': service_data.get('vehicleId'),
            'name': service_data.get('name'),
            'description': service_data.get('description'),
            'imageUrl': service_data.get('imageUrl'),
            'basePrice': service_data.get('basePrice', 0.0),
            'pricePerKm': service_data.get('pricePerKm', 0.0),
            'pricePerHour': service_data.get('pricePerHour', 0.0),
            'category': service_data.get('category', 'general'),
            'extraFields': service_data.get('extraFields'),
            'serviceBaseLatitude': service_data.get('serviceBaseLatitude'),
            'serviceBaseLongitude': service_data.get('serviceBaseLongitude'),
            'serviceBaseAddress': service_data.get('serviceBaseAddress'),
        }
        
        result = neo4j_driver.execute_write(query, params)
        if result and result[0]['s']:
            return Service._serialize_neo4j_data(result[0]['s'])
        return None
    
    @staticmethod
    def get_by_id(service_id: str) -> Optional[Dict[str, Any]]:
        """Get service by ID"""
        query = """
        MATCH (s:Service {id: $serviceId})
        OPTIONAL MATCH (p)-[:OFFERS]->(s)
        WHERE p:Provider OR p:User OR p:Seeker
        OPTIONAL MATCH (v:Vehicle)-[:PROVIDES]->(s)
        RETURN s, p.name as providerName, v.vehicleType as vehicleType
        """
        result = neo4j_driver.execute_read(query, {'serviceId': service_id})
        if result and result[0]['s']:
            service = Service._serialize_neo4j_data(result[0]['s'])
            service['providerName'] = result[0]['providerName']
            service['vehicleType'] = result[0]['vehicleType']
            return service
        return None
    
    @staticmethod
    def get_by_provider(provider_id: str) -> List[Dict[str, Any]]:
        """Get all services by a provider"""
        query = """
        MATCH (p)-[:OFFERS]->(s:Service)
        WHERE (p:Provider OR p:User OR p:Seeker) AND p.id = $providerId
        OPTIONAL MATCH (v:Vehicle)-[:PROVIDES]->(s)
        RETURN s, v.vehicleType as vehicleType, v.vehicleNumber as vehicleNumber
        ORDER BY s.createdAt DESC
        """
        result = neo4j_driver.execute_read(query, {'providerId': provider_id})
        services = []
        if result:
            for record in result:
                if record['s']:
                    service = Service._serialize_neo4j_data(record['s'])
                    service['vehicleType'] = record['vehicleType']
                    service['vehicleNumber'] = record['vehicleNumber']
                    services.append(service)
        return services
    
    @staticmethod
    def get_by_vehicle(vehicle_id: str) -> List[Dict[str, Any]]:
        """Get all services offered by a vehicle"""
        query = """
        MATCH (v:Vehicle {id: $vehicleId})-[:PROVIDES]->(s:Service)
        RETURN s
        ORDER BY s.createdAt DESC
        """
        result = neo4j_driver.execute_read(query, {'vehicleId': vehicle_id})
        services = []
        if result:
            for record in result:
                if record['s']:
                    services.append(Service._serialize_neo4j_data(record['s']))
        return services
    
    @staticmethod
    def get_available_services(
        category: Optional[str] = None,
        latitude: Optional[float] = None,
        longitude: Optional[float] = None,
        radius_km: float = 50.0
    ) -> List[Dict[str, Any]]:
        """Get all available services from verified providers"""
        # Providers can be stored under :Provider OR :User label (role='provider').
        # Matching only :Provider misses all :User-label providers → empty results.
        query = """
        MATCH (p)-[:OFFERS]->(s:Service)
        WHERE (p:Provider OR p:User)
          AND s.isActive = true
          AND coalesce(p.isActive, true) = true
          AND coalesce(p.isVerified, false) = true
        OPTIONAL MATCH (v:Vehicle)-[:PROVIDES]->(s)
        """

        params = {}

        if category:
            # Normalise both sides: replace underscores with spaces so that
            # "sand_trolley" matches a service whose category is "Sand Trolley".
            query += """
        WITH p, s, v
        WHERE toLower(replace(s.category, '_', ' ')) CONTAINS toLower(replace($category, '_', ' '))
           OR toLower(replace(coalesce(s.name, ''), '_', ' ')) CONTAINS toLower(replace($category, '_', ' '))
           OR toLower(replace(coalesce(v.vehicleType, ''), '_', ' ')) CONTAINS toLower(replace($category, '_', ' '))
        """
            params['category'] = category

        query += """
        // Calculate service-specific rating from feedback
        OPTIONAL MATCH (s)<-[:FOR_SERVICE]-(serviceFeedback:Feedback)
        WITH s, p, v,
             COALESCE(avg(serviceFeedback.rating), p.rating, 0.0) as serviceRating,
             count(serviceFeedback) as serviceReviewCount,
             p.rating as overallProviderRating,
             p.latitude as latitude, p.longitude as longitude
        RETURN s, p.id as providerId, p.name as providerName,
               serviceRating as providerRating,
               serviceReviewCount as totalReviews,
               overallProviderRating,
               p.profileImageUrl as providerImageUrl,
               v.id as vehicleId, v.vehicleType as vehicleType, v.vehicleNumber as vehicleNumber,
               v.vehicleImageBase64 as vehicleImageBase64,
               latitude, longitude,
               COALESCE(s.serviceBaseLatitude, p.latitude) as serviceBaseLatitude,
               COALESCE(s.serviceBaseLongitude, p.longitude) as serviceBaseLongitude,
               s.serviceBaseAddress as serviceBaseAddress
        ORDER BY s.createdAt DESC
        """
        
        result = neo4j_driver.execute_read(query, params)
        services = []
        if result:
            for record in result:
                if record['s']:
                    service = Service._serialize_neo4j_data(record['s'])
                    service_rating = record['providerRating']
                    review_count = record['totalReviews']

                    service['providerName'] = record['providerName']
                    service['providerRating'] = service_rating
                    service['totalReviews'] = review_count
                    service['providerImageUrl'] = record['providerImageUrl']
                    service['vehicleId'] = record['vehicleId']
                    service['vehicleType'] = record['vehicleType']
                    service['vehicleNumber'] = record['vehicleNumber']
                    service['vehicleImageBase64'] = record['vehicleImageBase64']
                    service['providerLatitude'] = record['latitude']
                    service['providerLongitude'] = record['longitude']
                    service['serviceBaseLatitude'] = record['serviceBaseLatitude']
                    service['serviceBaseLongitude'] = record['serviceBaseLongitude']
                    service['serviceBaseAddress'] = record['serviceBaseAddress']
                    service['distanceKm'] = None
                    services.append(service)

        # Distance-based filtering and sorting (Python-side; Neo4j CE has no spatial)
        if latitude is not None and longitude is not None:
            for svc in services:
                svc_lat = svc.get('serviceBaseLatitude')
                svc_lon = svc.get('serviceBaseLongitude')
                if svc_lat is not None and svc_lon is not None:
                    try:
                        svc['distanceKm'] = round(
                            _haversine_km(latitude, longitude, float(svc_lat), float(svc_lon)), 1
                        )
                    except Exception:
                        svc['distanceKm'] = None

            # Filter to radius (keep services without location — they show as "unknown distance")
            services = [
                s for s in services
                if s.get('distanceKm') is None or s['distanceKm'] <= radius_km
            ]
            # Sort: known distance ascending, unknown distance at end
            services.sort(key=lambda s: (s.get('distanceKm') is None, s.get('distanceKm') or 0))

        return services
    
    @staticmethod
    def update(service_id: str, update_data: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Update service"""
        set_clauses = ["s.updatedAt = datetime()"]
        params = {'serviceId': service_id}
        
        field_mapping = {
            'name': 'name',
            'description': 'description',
            'imageUrl': 'imageUrl',
            'basePrice': 'basePrice',
            'pricePerKm': 'pricePerKm',
            'pricePerHour': 'pricePerHour',
            'category': 'category',
            'isActive': 'isActive',
            'extraFields': 'extraFields',
            'serviceBaseLatitude': 'serviceBaseLatitude',
            'serviceBaseLongitude': 'serviceBaseLongitude',
            'serviceBaseAddress': 'serviceBaseAddress',
        }
        
        for key, neo4j_key in field_mapping.items():
            if key in update_data and update_data[key] is not None:
                set_clauses.append(f"s.{neo4j_key} = ${key}")
                params[key] = update_data[key]
        
        query = f"""
        MATCH (s:Service {{id: $serviceId}})
        SET {', '.join(set_clauses)}
        RETURN s
        """
        
        result = neo4j_driver.execute_write(query, params)
        if result and result[0]['s']:
            return Service._serialize_neo4j_data(result[0]['s'])
        return None
    
    @staticmethod
    def delete(service_id: str) -> bool:
        """Delete a service"""
        # Use RETURN 1 instead of count(s) — after DETACH DELETE the node is
        # out of scope and count(s) always returns 0, causing a false 404.
        query = """
        MATCH (s:Service {id: $serviceId})
        DETACH DELETE s
        RETURN 1 as deleted
        """
        result = neo4j_driver.execute_write(query, {'serviceId': service_id})
        return bool(result)
