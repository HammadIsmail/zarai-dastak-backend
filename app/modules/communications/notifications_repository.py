from typing import Optional, Dict, Any, List
import uuid
from datetime import datetime
from app.core.database.neo4j_driver import neo4j_driver


class Notification:
    @staticmethod
    def _serialize(node_data: Dict[str, Any]) -> Dict[str, Any]:
        from neo4j.time import DateTime as Neo4jDateTime
        result = {}
        for k, v in node_data.items():
            result[k] = v.to_native() if isinstance(v, Neo4jDateTime) else v
        return result

    @staticmethod
    def create(
        user_id: str,
        type: str,
        title: str,
        body: str,
        data: Optional[Dict[str, Any]] = None,
    ) -> Optional[Dict[str, Any]]:
        import json
        query = """
        CREATE (n:Notification {
            id: $id,
            userId: $userId,
            type: $type,
            title: $title,
            body: $body,
            data: $data,
            isRead: false,
            createdAt: datetime()
        })
        RETURN n
        """
        result = neo4j_driver.execute_write(query, {
            "id": str(uuid.uuid4()),
            "userId": user_id,
            "type": type,
            "title": title,
            "body": body,
            "data": json.dumps(data or {}),
        })
        if result and len(result) > 0:
            row = result[0]
            node = row.get('n') if hasattr(row, 'get') else row['n']
            if node:
                return Notification._serialize(dict(node))
        return None

    @staticmethod
    def get_for_user(user_id: str, limit: int = 50) -> List[Dict[str, Any]]:
        query = """
        MATCH (n:Notification {userId: $userId})
        RETURN n
        ORDER BY n.createdAt DESC
        LIMIT $limit
        """
        result = neo4j_driver.execute_read(query, {"userId": user_id, "limit": limit})
        notifications = []
        for row in (result or []):
            node = row.get('n') if hasattr(row, 'get') else row['n']
            if node:
                notifications.append(Notification._serialize(dict(node)))
        return notifications

    @staticmethod
    def get_unread_count(user_id: str) -> int:
        query = """
        MATCH (n:Notification {userId: $userId, isRead: false})
        RETURN count(n) AS unreadCount
        """
        result = neo4j_driver.execute_read(query, {"userId": user_id})
        if result and len(result) > 0:
            row = result[0]
            return int(row.get('unreadCount') if hasattr(row, 'get') else row['unreadCount'])
        return 0

    @staticmethod
    def mark_read(notification_id: str) -> bool:
        query = """
        MATCH (n:Notification {id: $id})
        SET n.isRead = true
        RETURN n
        """
        result = neo4j_driver.execute_write(query, {"id": notification_id})
        return bool(result)

    @staticmethod
    def mark_all_read(user_id: str) -> int:
        query = """
        MATCH (n:Notification {userId: $userId, isRead: false})
        SET n.isRead = true
        RETURN count(n) AS updated
        """
        result = neo4j_driver.execute_write(query, {"userId": user_id})
        if result and len(result) > 0:
            row = result[0]
            return int(row.get('updated') if hasattr(row, 'get') else row['updated'])
        return 0
