"""
Backward compatibility re-export.
Database drivers now live in `app.core.database`.
"""
from app.core.database import neo4j_driver, get_neo4j_driver, Neo4jDriver, get_redis, close_redis

__all__ = ['neo4j_driver', 'get_neo4j_driver', 'Neo4jDriver', 'get_redis', 'close_redis']
