"""
Message Model
Manages persisted chat messages between users
"""
import logging
from typing import Optional, Dict, Any, List
from datetime import datetime
from app.core.database.neo4j_driver import neo4j_driver
from app.core.constants import LIVE_COMMUNICATION_STATUSES

logger = logging.getLogger(__name__)


class Message:
    """Model for text messages between users"""
    
    def __init__(
        self,
        message_id: str,
        sender_id: str,
        receiver_id: str,
        booking_id: str,
        message_text: str,
        message_type: str = 'text',  # 'text', 'image', 'location'
        media_duration: Optional[int] = None,
        is_read: bool = False,
        created_at: Optional[datetime] = None,
        read_at: Optional[datetime] = None
    ):
        self.message_id = message_id
        self.sender_id = sender_id
        self.receiver_id = receiver_id
        self.booking_id = booking_id
        self.message_text = message_text
        self.message_type = message_type
        self.media_duration = media_duration
        self.is_read = is_read
        self.created_at = created_at or datetime.now()
        self.read_at = read_at

    @staticmethod
    def create_message(
        sender_id: str,
        receiver_id: str,
        booking_id: str,
        message_text: str,
        message_type: str = 'text',
        media_duration: Optional[int] = None,
    ) -> Optional[Dict[str, Any]]:
        """Create a new message.

        Symmetric: works regardless of whether sender is the seeker or the
        provider on the booking. Uses an OPTIONAL pre-flight check so the
        Cypher engine doesn't silently return zero rows on the first match —
        we can log exactly which precondition failed.
        """
        # Pre-flight: validate booking + participants separately so we can
        # tell the caller what's wrong instead of silently returning None.
        # WITH clauses make the variable scoping explicit and avoid Cypher
        # parser ambiguity when WHERE follows OPTIONAL MATCH.
        precheck_query = """
        OPTIONAL MATCH (b:Booking {id: $bookingId})
        WITH b
        OPTIONAL MATCH (sender)
            WHERE sender.id = $senderId
              AND (sender:Seeker OR sender:Provider OR sender:User)
        WITH b, sender
        OPTIONAL MATCH (receiver)
            WHERE receiver.id = $receiverId
              AND (receiver:Seeker OR receiver:Provider OR receiver:User)
        RETURN
            b IS NOT NULL AS bookingExists,
            sender IS NOT NULL AS senderExists,
            receiver IS NOT NULL AS receiverExists,
            coalesce(b.status, '') AS bookingStatus,
            coalesce(b.seekerId, '') AS bookingSeekerId,
            coalesce(b.providerId, '') AS bookingProviderId
        """
        precheck_params = {
            "senderId": sender_id,
            "receiverId": receiver_id,
            "bookingId": booking_id,
        }
        try:
            precheck = neo4j_driver.execute_read(precheck_query, precheck_params)
        except Exception:
            logger.exception("Message precheck query failed")
            precheck = []

        if precheck:
            row = precheck[0]
            booking_exists = row.get("bookingExists")
            sender_exists = row.get("senderExists")
            receiver_exists = row.get("receiverExists")
            booking_status = (row.get("bookingStatus") or "").lower()
            booking_seeker_id = row.get("bookingSeekerId") or ""
            booking_provider_id = row.get("bookingProviderId") or ""

            participants_match = (
                (booking_seeker_id == sender_id and booking_provider_id == receiver_id)
                or (booking_provider_id == sender_id and booking_seeker_id == receiver_id)
            )
            status_active = booking_status in LIVE_COMMUNICATION_STATUSES

            if not (booking_exists and sender_exists and receiver_exists and participants_match and status_active):
                logger.warning(
                    "Message create_message blocked: bookingExists=%s senderExists=%s receiverExists=%s "
                    "status=%r status_active=%s participants_match=%s "
                    "(senderId=%s receiverId=%s bookingId=%s bookingSeekerId=%s bookingProviderId=%s)",
                    booking_exists, sender_exists, receiver_exists,
                    booking_status, status_active, participants_match,
                    sender_id, receiver_id, booking_id,
                    booking_seeker_id, booking_provider_id,
                )
                return None

        query = """
        MATCH (sender) WHERE (sender:Seeker OR sender:Provider OR sender:User) AND sender.id = $senderId
        MATCH (receiver) WHERE (receiver:Seeker OR receiver:Provider OR receiver:User) AND receiver.id = $receiverId
        MATCH (b:Booking {id: $bookingId})
        WHERE toLower(coalesce(b.status, '')) IN $activeStatuses

        CREATE (m:Message {
            id: randomUUID(),
            senderId: $senderId,
            receiverId: $receiverId,
            bookingId: $bookingId,
            messageText: $messageText,
            messageType: $messageType,
            mediaDuration: $mediaDuration,
            isRead: false,
            createdAt: datetime()
        })

        CREATE (m)-[:SENT_BY]->(sender)
        CREATE (m)-[:SENT_TO]->(receiver)
        CREATE (m)-[:FOR_BOOKING]->(b)

         RETURN m,
             sender.name as senderName, sender.phone as senderPhone,
             sender.role as senderRole,
             coalesce(sender.profileImageUrl, sender.profile_image_url, '') as senderProfileImageUrl,
             receiver.name as receiverName, receiver.phone as receiverPhone,
             receiver.role as receiverRole,
             coalesce(receiver.profileImageUrl, receiver.profile_image_url, '') as receiverProfileImageUrl
        """

        params = {
            "senderId": sender_id,
            "receiverId": receiver_id,
            "bookingId": booking_id,
            "messageText": message_text,
            "messageType": message_type,
            "mediaDuration": media_duration,
            "activeStatuses": list(LIVE_COMMUNICATION_STATUSES),
        }

        try:
            result = neo4j_driver.execute_write(query, params)
        except Exception:
            logger.exception(
                "Message create_message write failed (senderId=%s receiverId=%s bookingId=%s)",
                sender_id, receiver_id, booking_id,
            )
            return None

        if result and len(result) > 0:
            message_record = result[0].get('m')
            if message_record:
                message = Message._serialize_neo4j_data(message_record)
                message['senderName'] = result[0].get('senderName')
                message['senderPhone'] = result[0].get('senderPhone')
                message['senderRole'] = result[0].get('senderRole')
                message['senderProfileImageUrl'] = result[0].get('senderProfileImageUrl') or None
                message['receiverName'] = result[0].get('receiverName')
                message['receiverPhone'] = result[0].get('receiverPhone')
                message['receiverRole'] = result[0].get('receiverRole')
                message['receiverProfileImageUrl'] = result[0].get('receiverProfileImageUrl') or None
                return message

        logger.warning(
            "Message create_message returned no rows despite precheck passing "
            "(senderId=%s receiverId=%s bookingId=%s)",
            sender_id, receiver_id, booking_id,
        )
        return None

    @staticmethod
    def get_messages_for_booking(
        booking_id: str,
        limit: int = 100
    ) -> List[Dict[str, Any]]:
        """Get all messages for a booking"""
        query = """
        MATCH (m:Message {bookingId: $bookingId})
        OPTIONAL MATCH (m)-[:SENT_BY]->(sender)
        OPTIONAL MATCH (m)-[:SENT_TO]->(receiver)
           WITH m,
               sender.name as senderName, sender.phone as senderPhone,
               sender.role as senderRole,
               coalesce(sender.profileImageUrl, sender.profile_image_url, '') as senderProfileImageUrl,
               receiver.name as receiverName, receiver.phone as receiverPhone,
               receiver.role as receiverRole,
               coalesce(receiver.profileImageUrl, receiver.profile_image_url, '') as receiverProfileImageUrl
           RETURN m, senderName, senderPhone, senderRole, senderProfileImageUrl, receiverName, receiverPhone, receiverRole, receiverProfileImageUrl
        ORDER BY m.createdAt ASC
        LIMIT $limit
        """
        
        result = neo4j_driver.execute_read(query, {"bookingId": booking_id, "limit": limit})
        
        messages = []
        if result:
            for record in result:
                if record['m']:
                    msg = Message._serialize_neo4j_data(record['m'])
                    msg['senderName'] = record['senderName']
                    msg['senderPhone'] = record['senderPhone']
                    msg['senderRole'] = record.get('senderRole')
                    msg['senderProfileImageUrl'] = record.get('senderProfileImageUrl') or None
                    msg['receiverName'] = record['receiverName']
                    msg['receiverPhone'] = record['receiverPhone']
                    msg['receiverRole'] = record.get('receiverRole')
                    msg['receiverProfileImageUrl'] = record.get('receiverProfileImageUrl') or None
                    messages.append(msg)
        
        return messages

    @staticmethod
    def get_user_conversations(user_id: str, limit: int = 50) -> List[Dict[str, Any]]:
        """Get latest conversation summaries for a user across bookings."""
        query = """
        MATCH (m:Message)
        WHERE m.senderId = $userId OR m.receiverId = $userId
        WITH m,
             CASE WHEN m.senderId = $userId THEN m.receiverId ELSE m.senderId END AS otherUserId
        ORDER BY m.createdAt DESC
        WITH otherUserId, collect(m)[0] AS lastMsg, collect(m) AS allMsgs
        OPTIONAL MATCH (u) WHERE (u:Seeker OR u:Provider OR u:User) AND u.id = otherUserId
        RETURN
            otherUserId,
            coalesce(u.name, 'User') AS otherUserName,
            coalesce(u.profileImageUrl, u.profile_image_url, '') AS otherUserImage,
            lastMsg,
            size([msg IN allMsgs WHERE msg.receiverId = $userId AND NOT msg.isRead]) AS unreadCount
        ORDER BY lastMsg.createdAt DESC
        LIMIT $limit
        """

        result = neo4j_driver.execute_read(query, {"userId": user_id, "limit": limit})
        conversations: List[Dict[str, Any]] = []

        if not result:
            return conversations

        for row in result:
            last = Message._serialize_neo4j_data(row.get("lastMsg") or {})
            booking_id = str(last.get("bookingId") or "")
            other_user_id = str(row.get("otherUserId") or "")
            if not booking_id or not other_user_id:
                continue

            conversations.append(
                {
                    "id": f"{booking_id}:{other_user_id}",
                    "bookingId": booking_id,
                    "otherUserId": other_user_id,
                    "otherUserName": row.get("otherUserName") or "User",
                    "otherUserImage": (row.get("otherUserImage") or "") or None,
                    "lastMessage": {
                        "id": str(last.get("id") or ""),
                        "senderId": str(last.get("senderId") or ""),
                        "senderName": str(last.get("senderName") or "User"),
                        "message": str(last.get("messageText") or ""),
                        "messageType": str(last.get("messageType") or "text"),
                        "imageUrl": str(last.get("messageText") or "") if str(last.get("messageType") or "") == "image" else None,
                        "voiceUrl": str(last.get("messageText") or "") if str(last.get("messageType") or "") == "voice" else None,
                        "voiceDuration": last.get("mediaDuration"),
                        "timestamp": last.get("createdAt"),
                        "isRead": bool(last.get("isRead") is True),
                    },
                    "unreadCount": int(row.get("unreadCount") or 0),
                    "updatedAt": last.get("createdAt"),
                }
            )

        return conversations

    @staticmethod
    def get_conversation_messages(
        user1_id: str,
        user2_id: str,
        booking_id: str,
        limit: int = 100
    ) -> List[Dict[str, Any]]:
        """Get all messages between two users for a specific booking"""
        query = """
        MATCH (m:Message {bookingId: $bookingId})
        WHERE (m.senderId = $user1Id AND m.receiverId = $user2Id)
           OR (m.senderId = $user2Id AND m.receiverId = $user1Id)
        OPTIONAL MATCH (m)-[:SENT_BY]->(sender)
        OPTIONAL MATCH (m)-[:SENT_TO]->(receiver)
           WITH m,
               sender.name as senderName,
               sender.role as senderRole,
               coalesce(sender.profileImageUrl, sender.profile_image_url, '') as senderProfileImageUrl,
               receiver.name as receiverName,
               receiver.role as receiverRole,
               coalesce(receiver.profileImageUrl, receiver.profile_image_url, '') as receiverProfileImageUrl
           RETURN m, senderName, senderRole, senderProfileImageUrl, receiverName, receiverRole, receiverProfileImageUrl
        ORDER BY m.createdAt ASC
        LIMIT $limit
        """
        
        result = neo4j_driver.execute_read(query, {
            "user1Id": user1_id,
            "user2Id": user2_id,
            "bookingId": booking_id,
            "limit": limit
        })
        
        messages = []
        if result:
            for record in result:
                if record['m']:
                    msg = Message._serialize_neo4j_data(record['m'])
                    msg['senderName'] = record['senderName']
                    msg['senderRole'] = record.get('senderRole')
                    msg['senderProfileImageUrl'] = record.get('senderProfileImageUrl') or None
                    msg['receiverName'] = record['receiverName']
                    msg['receiverRole'] = record.get('receiverRole')
                    msg['receiverProfileImageUrl'] = record.get('receiverProfileImageUrl') or None
                    messages.append(msg)
        
        return messages

    @staticmethod
    def mark_as_read(message_id: str) -> bool:
        """Mark a message as read"""
        query = """
        MATCH (m:Message {id: $messageId})
        SET m.isRead = true, m.readAt = datetime()
        RETURN m
        """
        
        result = neo4j_driver.execute_write(query, {"messageId": message_id})
        return result is not None and len(result) > 0

    @staticmethod
    def mark_all_as_read(receiver_id: str, booking_id: str) -> bool:
        """Mark all messages for a receiver in a booking as read"""
        query = """
        MATCH (m:Message {receiverId: $receiverId, bookingId: $bookingId, isRead: false})
        SET m.isRead = true, m.readAt = datetime()
        RETURN count(m) as updatedCount
        """
        
        result = neo4j_driver.execute_write(query, {
            "receiverId": receiver_id,
            "bookingId": booking_id
        })
        return result is not None and len(result) > 0

    @staticmethod
    def get_unread_count(user_id: str, booking_id: Optional[str] = None) -> int:
        """Get count of unread messages for a user"""
        if booking_id:
            query = """
            MATCH (m:Message {receiverId: $userId, bookingId: $bookingId, isRead: false})
            RETURN count(m) as unreadCount
            """
            result = neo4j_driver.execute_read(query, {
                "userId": user_id,
                "bookingId": booking_id
            })
        else:
            query = """
            MATCH (m:Message {receiverId: $userId, isRead: false})
            RETURN count(m) as unreadCount
            """
            result = neo4j_driver.execute_read(query, {"userId": user_id})
        
        if result and len(result) > 0:
            return result[0].get('unreadCount', 0)
        
        return 0

    @staticmethod
    def _serialize_neo4j_data(data: Dict[str, Any]) -> Dict[str, Any]:
        """Convert Neo4j data to JSON-serializable format"""
        from neo4j.time import DateTime as Neo4jDateTime
        
        result = {}
        for key, value in data.items():
            if isinstance(value, Neo4jDateTime):
                result[key] = value.to_native().isoformat()
            elif value is None:
                result[key] = None
            else:
                result[key] = value
        return result
