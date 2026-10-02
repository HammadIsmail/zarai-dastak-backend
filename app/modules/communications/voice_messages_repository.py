"""
Voice Message Model
Manages voice message storage and retrieval
"""
from typing import Optional, Dict, Any, List
from datetime import datetime
from app.core.database.neo4j_driver import neo4j_driver


class VoiceMessage:
    def __init__(
        self,
        message_id: str,
        sender_id: str,
        receiver_id: str,
        booking_id: str,
        audio_url: str,
        duration: int,  # in seconds
        is_read: bool = False,
        created_at: Optional[datetime] = None
    ):
        self.message_id = message_id
        self.sender_id = sender_id
        self.receiver_id = receiver_id
        self.booking_id = booking_id
        self.audio_url = audio_url
        self.duration = duration
        self.is_read = is_read
        self.created_at = created_at or datetime.now()

    @staticmethod
    def create_voice_message(
        sender_id: str,
        receiver_id: str,
        booking_id: str,
        audio_url: str,
        duration: int
    ) -> Optional[Dict[str, Any]]:
        """Create a new voice message"""
        query = """
        MATCH (sender) WHERE (sender:Seeker OR sender:Provider OR sender:User) AND sender.id = $senderId
        MATCH (receiver) WHERE (receiver:Seeker OR receiver:Provider OR receiver:User) AND receiver.id = $receiverId
        MATCH (b:Booking {id: $bookingId})
        
        CREATE (vm:VoiceMessage {
            id: randomUUID(),
            senderId: $senderId,
            receiverId: $receiverId,
            bookingId: $bookingId,
            audioUrl: $audioUrl,
            duration: $duration,
            isRead: false,
            createdAt: datetime()
        })
        
        CREATE (vm)-[:SENT_BY]->(sender)
        CREATE (vm)-[:SENT_TO]->(receiver)
        CREATE (vm)-[:FOR_BOOKING]->(b)
        
         RETURN vm,
             sender.name as senderName,
             sender.role as senderRole,
             coalesce(sender.profileImageUrl, sender.profile_image_url, '') as senderProfileImageUrl,
             receiver.name as receiverName,
             receiver.role as receiverRole,
             coalesce(receiver.profileImageUrl, receiver.profile_image_url, '') as receiverProfileImageUrl
        """
        
        params = {
            "senderId": sender_id,
            "receiverId": receiver_id,
            "bookingId": booking_id,
            "audioUrl": audio_url,
            "duration": duration
        }
        
        result = neo4j_driver.execute_write(query, params)
        
        if result and len(result) > 0:
            vm_record = result[0].get('vm')
            if vm_record:
                voice_message = VoiceMessage._serialize_neo4j_data(vm_record)
                voice_message['senderName'] = result[0].get('senderName')
                voice_message['senderRole'] = result[0].get('senderRole')
                voice_message['senderProfileImageUrl'] = result[0].get('senderProfileImageUrl') or None
                voice_message['receiverName'] = result[0].get('receiverName')
                voice_message['receiverRole'] = result[0].get('receiverRole')
                voice_message['receiverProfileImageUrl'] = result[0].get('receiverProfileImageUrl') or None
                return voice_message
        
        return None

    @staticmethod
    def get_voice_messages_for_booking(
        booking_id: str,
        limit: int = 50
    ) -> List[Dict[str, Any]]:
        """Get all voice messages for a booking"""
        query = """
        MATCH (vm:VoiceMessage {bookingId: $bookingId})
        OPTIONAL MATCH (vm)-[:SENT_BY]->(sender)
        OPTIONAL MATCH (vm)-[:SENT_TO]->(receiver)
           WITH vm,
               sender.name as senderName,
               sender.role as senderRole,
               coalesce(sender.profileImageUrl, sender.profile_image_url, '') as senderProfileImageUrl,
               receiver.name as receiverName,
               receiver.role as receiverRole,
               coalesce(receiver.profileImageUrl, receiver.profile_image_url, '') as receiverProfileImageUrl
           RETURN vm, senderName, senderRole, senderProfileImageUrl, receiverName, receiverRole, receiverProfileImageUrl
        ORDER BY vm.createdAt DESC
        LIMIT $limit
        """
        
        result = neo4j_driver.execute_read(query, {"bookingId": booking_id, "limit": limit})
        
        messages = []
        if result:
            for record in result:
                if record['vm']:
                    vm = VoiceMessage._serialize_neo4j_data(record['vm'])
                    vm['senderName'] = record['senderName']
                    vm['senderRole'] = record.get('senderRole')
                    vm['senderProfileImageUrl'] = record.get('senderProfileImageUrl') or None
                    vm['receiverName'] = record['receiverName']
                    vm['receiverRole'] = record.get('receiverRole')
                    vm['receiverProfileImageUrl'] = record.get('receiverProfileImageUrl') or None
                    messages.append(vm)
        
        return messages

    @staticmethod
    def mark_as_read(message_id: str) -> bool:
        """Mark a voice message as read"""
        query = """
        MATCH (vm:VoiceMessage {id: $messageId})
        SET vm.isRead = true, vm.readAt = datetime()
        RETURN vm
        """
        
        result = neo4j_driver.execute_write(query, {"messageId": message_id})
        return result is not None and len(result) > 0

    @staticmethod
    def get_unread_count(user_id: str) -> int:
        """Get count of unread voice messages for a user"""
        query = """
        MATCH (vm:VoiceMessage {receiverId: $userId, isRead: false})
        RETURN count(vm) as unreadCount
        """
        
        result = neo4j_driver.execute_read(query, {"userId": user_id})
        
        if result and len(result) > 0:
            return result[0].get('unreadCount', 0)
        
        return 0

    @staticmethod
    def _serialize_neo4j_data(data: Dict[str, Any]) -> Dict[str, Any]:
        """Convert Neo4j data to JSON-serializable format"""
        result = {}
        for key, value in data.items():
            if hasattr(value, 'iso_format'):  # Neo4j DateTime
                result[key] = value.iso_format()
            else:
                result[key] = value
        return result
