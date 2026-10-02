import time
from neo4j import GraphDatabase
from neo4j.exceptions import ServiceUnavailable, SessionExpired
from typing import Optional
from ..config import settings
import logging

logger = logging.getLogger(__name__)

_INDEX_QUERIES = [
    "CREATE INDEX msg_sender IF NOT EXISTS FOR (m:Message) ON (m.senderId)",
    "CREATE INDEX msg_receiver IF NOT EXISTS FOR (m:Message) ON (m.receiverId)",
    "CREATE INDEX msg_booking IF NOT EXISTS FOR (m:Message) ON (m.bookingId)",
    "CREATE INDEX call_caller IF NOT EXISTS FOR (c:Call) ON (c.callerId)",
    "CREATE INDEX call_receiver IF NOT EXISTS FOR (c:Call) ON (c.receiverId)",
    "CREATE INDEX seeker_id IF NOT EXISTS FOR (s:Seeker) ON (s.id)",
    "CREATE INDEX user_id IF NOT EXISTS FOR (u:User) ON (u.id)",
    "CREATE INDEX provider_id IF NOT EXISTS FOR (p:Provider) ON (p.id)",
    "CREATE INDEX booking_seeker IF NOT EXISTS FOR (b:Booking) ON (b.seekerId)",
    "CREATE INDEX booking_provider IF NOT EXISTS FOR (b:Booking) ON (b.providerId)",
    "CREATE INDEX booking_status IF NOT EXISTS FOR (b:Booking) ON (b.status)",
    "CREATE INDEX location_composite IF NOT EXISTS FOR (l:Location) ON (l.userId, l.bookingId)",
    # Service indexes — critical for getAvailableServices and recommendations
    "CREATE INDEX service_active IF NOT EXISTS FOR (s:Service) ON (s.isActive)",
    "CREATE INDEX service_category IF NOT EXISTS FOR (s:Service) ON (s.category)",
    "CREATE INDEX service_provider IF NOT EXISTS FOR (s:Service) ON (s.providerId)",
    "CREATE INDEX service_created IF NOT EXISTS FOR (s:Service) ON (s.createdAt)",
    "CREATE INDEX vehicle_id IF NOT EXISTS FOR (v:Vehicle) ON (v.id)",
]


class Neo4jDriver:
    """Singleton Neo4j database driver"""
    
    _instance: Optional['Neo4jDriver'] = None
    _driver: Optional[GraphDatabase.driver] = None
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(Neo4jDriver, cls).__new__(cls)
            cls._instance._initialize()
        return cls._instance
    
    def _initialize(self):
        """Initialize Neo4j driver"""
        try:
            uri = self._normalize_neo4j_uri(settings.NEO4J_URI)
            pwd = settings.NEO4J_PASSWORD
            logger.warning(
                "[NEO4J] uri=%s user=%r pwd_len=%d pwd_prefix=%s",
                uri, settings.NEO4J_USERNAME, len(pwd),
                pwd[:4] if len(pwd) >= 4 else "???"
            )
            self._driver = GraphDatabase.driver(
                uri,
                auth=(settings.NEO4J_USERNAME, settings.NEO4J_PASSWORD),
                max_connection_lifetime=3600,
                max_connection_pool_size=50,
                connection_acquisition_timeout=60
            )
            logger.info("Neo4j driver initialized for %s", uri)
        except Exception as e:
            logger.error(f"Failed to initialize Neo4j driver: {str(e)}", exc_info=True)
            self._driver = None

    @staticmethod
    def _normalize_neo4j_uri(raw_uri: str) -> str:
        """Normalize Neo4j URI to a driver-compatible value."""
        uri = (raw_uri or '').strip()
        if not uri:
            return 'bolt://localhost:7687'

        if '://' in uri:
            if uri.startswith("neo4j+s://"):
                return "neo4j+ssc://" + uri[len("neo4j+s://"):]
            return uri

        host = uri.split(':')[0]
        if host.endswith('.databases.neo4j.io'):
            return f'neo4j+ssc://{host}'

        return f'bolt://{uri}'
    
    def get_session(self):
        """Get a new Neo4j session"""
        if self._driver is None:
            self._initialize()
        if self._driver is None:
            raise Exception("Neo4j driver not initialized")
        # For Aura (neo4j+s:// or neo4j+ssc://), don't specify database - use default
        if settings.NEO4J_URI.startswith(("neo4j+s://", "neo4j+ssc://")):
            return self._driver.session()
        return self._driver.session(database=settings.NEO4J_DATABASE)
    
    def ensure_indexes(self) -> None:
        """Create all required indexes if they don't exist. Called once at startup."""
        with self.get_session() as session:
            for query in _INDEX_QUERIES:
                try:
                    session.run(query)
                except Exception as exc:
                    logger.warning("Index creation skipped: %s — %s", query, exc)

    def close(self):
        """Close Neo4j driver"""
        if self._driver:
            self._driver.close()
            self._driver = None

    def verify_connectivity(self):
        """Verify database connectivity"""
        if self._driver is None:
            self._initialize()
        if self._driver is None:
            return False
            
        try:
            # Direct query test (works better than driver.verify_connectivity for Aura)
            session = None
            if settings.NEO4J_URI.startswith(("neo4j+s://", "neo4j+ssc://")):
                session = self._driver.session()
            else:
                session = self._driver.session(database=settings.NEO4J_DATABASE)
            
            with session:
                result = session.run("RETURN 1 AS num")
                record = result.single()
                if record and record["num"] == 1:
                    return True
                    
            return False
                
        except Exception as e:
            error_msg = str(e)
            logger.warning(f"Neo4j connection verification failed: {error_msg}")
            return False
    
    def execute_query(self, query: str, parameters: dict = None):
        """Execute a Cypher query"""
        with self.get_session() as session:
            result = session.run(query, parameters or {})
            return [record.data() for record in result]
    
    def execute_write(self, query: str, parameters: dict = None):
        """Execute a write transaction with exponential-backoff retry on transient errors."""
        last_exc: Exception | None = None
        for attempt in range(3):
            try:
                with self.get_session() as session:
                    def transaction_function(tx):
                        result = tx.run(query, parameters or {})
                        return [record.data() for record in result]
                    return session.execute_write(transaction_function)
            except (ServiceUnavailable, SessionExpired) as exc:
                last_exc = exc
                if attempt < 2:
                    time.sleep(0.25 * (2 ** attempt))
        raise last_exc

    def execute_read(self, query: str, parameters: dict = None):
        """Execute a read transaction with exponential-backoff retry on transient errors."""
        last_exc: Exception | None = None
        for attempt in range(3):
            try:
                with self.get_session() as session:
                    def transaction_function(tx):
                        result = tx.run(query, parameters or {})
                        return [record.data() for record in result]
                    return session.execute_read(transaction_function)
            except (ServiceUnavailable, SessionExpired) as exc:
                last_exc = exc
                if attempt < 2:
                    time.sleep(0.25 * (2 ** attempt))
        raise last_exc


# Create singleton instance
neo4j_driver = Neo4jDriver()


def get_neo4j_driver() -> Neo4jDriver:
    """Get Neo4j driver instance"""
    return neo4j_driver
