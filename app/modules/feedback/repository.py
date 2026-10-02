from typing import Optional, Dict, Any, List
from datetime import datetime
from app.core.database.neo4j_driver import neo4j_driver


class Feedback:
    """Feedback model for service reviews and ratings"""
    
    def __init__(
        self,
        id: str,
        booking_id: str,
        provider_id: str,
        seeker_id: str,
        reviewer_id: str,
        reviewer_type: str,  # 'provider' or 'seeker'
        rating: float,
        comment: Optional[str] = None,
        created_at: Optional[datetime] = None,
    ):
        self.id = id
        self.booking_id = booking_id
        self.provider_id = provider_id
        self.seeker_id = seeker_id
        self.reviewer_id = reviewer_id
        self.reviewer_type = reviewer_type
        self.rating = rating
        self.comment = comment
        self.created_at = created_at or datetime.now()
    
    @staticmethod
    def create_provider_feedback(
        booking_id: str,
        provider_id: str,
        seeker_id: str,
        rating: float,
        comment: Optional[str] = None
    ) -> Optional[Dict[str, Any]]:
        """Seeker gives feedback about provider after service completion"""
        query = """
        MATCH (b:Booking {
            id: $bookingId,
            status: 'completed',
            providerId: $providerId,
            seekerId: $seekerId
        })
        MATCH (provider)
        WHERE (provider:Provider OR provider:User OR provider:Seeker) AND provider.id = $providerId
        MATCH (seeker)
        WHERE (seeker:Seeker OR seeker:User OR seeker:Provider) AND seeker.id = $seekerId
        OPTIONAL MATCH (service:Service {id: b.serviceId})
        
        CREATE (f:Feedback {
            id: randomUUID(),
            bookingId: $bookingId,
            providerId: $providerId,
            seekerId: $seekerId,
            reviewerId: $seekerId,
            reviewerType: 'seeker',
            reviewerName: seeker.name,
            serviceId: b.serviceId,
            rating: $rating,
            comment: $comment,
            createdAt: datetime()
        })
        
        CREATE (f)-[:ABOUT]->(provider)
        CREATE (f)-[:GIVEN_BY]->(seeker)
        CREATE (f)-[:FOR_BOOKING]->(b)
        FOREACH (_ IN CASE WHEN service IS NOT NULL THEN [1] ELSE [] END |
            CREATE (f)-[:FOR_SERVICE]->(service)
        )
        
        SET b.providerRating = $rating,
            b.providerReview = $comment
        
        // Update provider's overall rating
        WITH provider, f, seeker
        OPTIONAL MATCH (provider)<-[:ABOUT]-(allFeedback:Feedback)
        WITH provider, f, seeker, avg(allFeedback.rating) as avgRating, count(allFeedback) as totalReviews
        SET provider.rating = avgRating,
            provider.totalReviews = totalReviews
        
        RETURN f, seeker.name as reviewerName
        """
        
        params = {
            "bookingId": booking_id,
            "providerId": provider_id,
            "seekerId": seeker_id,
            "rating": float(rating),
            "comment": comment
        }
        
        result = neo4j_driver.execute_write(query, params)
        
        if result and len(result) > 0:
            feedback_record = result[0].get('f')
            if feedback_record:
                feedback = Feedback._serialize_neo4j_data(feedback_record)
                feedback['reviewerName'] = result[0].get('reviewerName')
                return feedback
        return None
    
    @staticmethod
    def create_seeker_feedback(
        booking_id: str,
        provider_id: str,
        seeker_id: str,
        rating: float,
        comment: Optional[str] = None
    ) -> Optional[Dict[str, Any]]:
        """Provider gives feedback about seeker after service completion"""
        query = """
        MATCH (b:Booking {
            id: $bookingId,
            status: 'completed',
            providerId: $providerId,
            seekerId: $seekerId
        })
        MATCH (provider)
        WHERE (provider:Provider OR provider:User OR provider:Seeker) AND provider.id = $providerId
        MATCH (seeker)
        WHERE (seeker:Seeker OR seeker:User OR seeker:Provider) AND seeker.id = $seekerId
        OPTIONAL MATCH (service:Service {id: b.serviceId})
        
        CREATE (f:Feedback {
            id: randomUUID(),
            bookingId: $bookingId,
            providerId: $providerId,
            seekerId: $seekerId,
            reviewerId: $providerId,
            reviewerType: 'provider',
            reviewerName: provider.name,
            serviceId: b.serviceId,
            rating: $rating,
            comment: $comment,
            createdAt: datetime()
        })
        
        CREATE (f)-[:ABOUT]->(seeker)
        CREATE (f)-[:GIVEN_BY]->(provider)
        CREATE (f)-[:FOR_BOOKING]->(b)
        FOREACH (_ IN CASE WHEN service IS NOT NULL THEN [1] ELSE [] END |
            CREATE (f)-[:FOR_SERVICE]->(service)
        )
        
        SET b.seekerRating = $rating,
            b.seekerReview = $comment
        
        WITH seeker, f, provider
        OPTIONAL MATCH (seeker)<-[:ABOUT]-(allFeedback:Feedback)
        WITH seeker, f, provider, avg(allFeedback.rating) as avgRating, count(allFeedback) as totalReviews
        SET seeker.rating = avgRating,
            seeker.totalReviews = totalReviews
        
        RETURN f, provider.name as reviewerName
        """
        
        params = {
            "bookingId": booking_id,
            "providerId": provider_id,
            "seekerId": seeker_id,
            "rating": float(rating),
            "comment": comment
        }
        result = neo4j_driver.execute_write(query, params)
        if result and result[0].get('f'):
            feedback = Feedback._serialize_neo4j_data(result[0]['f'])
            feedback['reviewerName'] = result[0].get('reviewerName')
            return feedback
        return None
    
    @staticmethod
    def get_provider_feedbacks(provider_id: str, limit: int = 50) -> List[Dict[str, Any]]:
        """Get all feedback for a provider"""
        query = """
        MATCH (f:Feedback)-[:ABOUT]->(provider)
        WHERE provider.id = $providerId
        OPTIONAL MATCH (f)-[:GIVEN_BY]->(reviewer)
        RETURN f, COALESCE(reviewer.name, f.reviewerName) as reviewerName
        ORDER BY f.createdAt DESC
        LIMIT $limit
        """
        
        result = neo4j_driver.execute_read(query, {"providerId": provider_id, "limit": limit})
        feedbacks = []
        for record in result:
            feedback = Feedback._serialize_neo4j_data(record['f'])
            feedback['reviewerName'] = record.get('reviewerName')
            feedbacks.append(feedback)
        return feedbacks
    
    @staticmethod
    def get_seeker_feedbacks(seeker_id: str, limit: int = 50) -> List[Dict[str, Any]]:
        """Get all feedback for a seeker"""
        query = """
        MATCH (f:Feedback)-[:ABOUT]->(seeker)
        WHERE seeker.id = $seekerId
        OPTIONAL MATCH (f)-[:GIVEN_BY]->(reviewer)
        RETURN f, COALESCE(reviewer.name, f.reviewerName) as reviewerName
        ORDER BY f.createdAt DESC
        LIMIT $limit
        """
        
        result = neo4j_driver.execute_read(query, {"seekerId": seeker_id, "limit": limit})
        feedbacks = []
        for record in result:
            feedback = Feedback._serialize_neo4j_data(record['f'])
            feedback['reviewerName'] = record.get('reviewerName')
            feedbacks.append(feedback)
        return feedbacks
    
    @staticmethod
    def check_feedback_exists(booking_id: str, reviewer_type: str) -> bool:
        """Check if feedback already exists for a booking from specific reviewer type"""
        query = """
        MATCH (f:Feedback {bookingId: $bookingId, reviewerType: $reviewerType})
        RETURN count(f) as total
        """
        
        result = neo4j_driver.execute_read(query, {
            "bookingId": booking_id,
            "reviewerType": reviewer_type
        })
        exists = (result[0]['total'] > 0) if result else False
        return exists
    
    @staticmethod
    def delete_feedback(feedback_id: str) -> Optional[Dict[str, Any]]:
        """
        Delete a feedback node and recalculate the target user's rating.
        Returns the deleted feedback dict on success, None if not found.
        """
        query = """
        MATCH (f:Feedback {id: $feedbackId})

        // Determine who the feedback is about
        OPTIONAL MATCH (f)-[:ABOUT]->(target)

        WITH f, target, f.reviewerType AS reviewerType

        // Detach and delete the feedback
        DETACH DELETE f

        // Recalculate the target's rating from remaining feedbacks
        WITH target, reviewerType
        WHERE target IS NOT NULL
        OPTIONAL MATCH (target)<-[:ABOUT]-(remaining:Feedback)
        WITH target, reviewerType,
             CASE WHEN count(remaining) > 0 THEN avg(remaining.rating) ELSE 0.0 END AS newAvgRating,
             count(remaining) AS newTotalReviews
        SET target.rating = newAvgRating,
            target.totalReviews = newTotalReviews

        RETURN newAvgRating, newTotalReviews, target.id AS targetId
        """
        result = neo4j_driver.execute_write(query, {"feedbackId": feedback_id})
        if result and len(result) > 0:
            return {
                "targetId": result[0].get("targetId"),
                "newRating": result[0].get("newAvgRating", 0.0),
                "newTotalReviews": result[0].get("newTotalReviews", 0),
            }
        return None

    @staticmethod
    def get_feedback_by_id(feedback_id: str) -> Optional[Dict[str, Any]]:
        """Get a single feedback node by ID."""
        query = """
        MATCH (f:Feedback {id: $feedbackId})
        RETURN f
        """
        result = neo4j_driver.execute_read(query, {"feedbackId": feedback_id})
        if result and result[0].get("f"):
            return Feedback._serialize_neo4j_data(result[0]["f"])
        return None

    @staticmethod
    def _serialize_neo4j_data(data: Dict[str, Any]) -> Dict[str, Any]:
        """Convert Neo4j data types to Python types"""
        from neo4j.time import DateTime as Neo4jDateTime
        
        serialized = {}
        for key, value in data.items():
            if isinstance(value, Neo4jDateTime):
                serialized[key] = value.to_native()
            elif value is None:
                serialized[key] = None
            else:
                serialized[key] = value
        return serialized
