import asyncio

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette_graphene3 import GraphQLApp, make_graphiql_handler
import socketio
import uvicorn
import logging

from app.core.config import settings
from app.core.database import neo4j_driver
from app.core.database.redis_client import close_redis
from app.core.realtime.websocket_gateway import router as realtime_router
from app.core.realtime.socketio_gateway import sio
from app.modules import api_router, otp_router
from .graphql.schema import schema

# Configure logging with cleaner format
logging.basicConfig(
    level=logging.ERROR,
    format='%(levelname)s: %(message)s'
)

# Suppress verbose third-party library logs
logging.getLogger('neo4j').setLevel(logging.ERROR)
logging.getLogger('neo4j.pool').setLevel(logging.ERROR)
logging.getLogger('neo4j.io').setLevel(logging.ERROR)
logging.getLogger('neo4j.notifications').setLevel(logging.ERROR)  # Only show errors for notifications
logging.getLogger('urllib3').setLevel(logging.ERROR)
logging.getLogger('cachecontrol').setLevel(logging.ERROR)
logging.getLogger('graphql').setLevel(logging.ERROR)

# Application logger
logger = logging.getLogger(__name__)
logger.setLevel(logging.ERROR)


# Initialize FastAPI app
app = FastAPI(
    title=settings.APP_NAME,
    version=settings.VERSION,
    debug=settings.DEBUG,
)

# Add validation error handler
@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    return JSONResponse(
        status_code=422,
        content={"detail": exc.errors()}
    )

# Configure CORS - Must be before other middleware
# Use allow_origin_regex to allow all origins (works better with credentials)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.ALLOWED_ORIGINS,
    allow_origin_regex=".*" if settings.ALLOWED_ORIGINS == ["*"] else None,
    allow_credentials=True,
    allow_methods=["*"],  # Allow all methods (GET, POST, PUT, DELETE, OPTIONS, etc.)
    allow_headers=["*"],  # Allow all headers
    expose_headers=["*"],  # Expose all headers to the client
    max_age=3600,  # Cache preflight requests for 1 hour
)


# Include REST API routers
app.include_router(api_router)
app.include_router(otp_router)
app.include_router(realtime_router)


# Health check endpoint
@app.get("/health")
async def health_check():
    """Health check endpoint"""
    neo4j_status = neo4j_driver.verify_connectivity()
    
    return {
        "status": "healthy" if neo4j_status else "degraded",
        "version": settings.VERSION,
        "database": {
            "neo4j": "connected" if neo4j_status else "disconnected"
        }
    }


# Root endpoint
@app.get("/")
async def root():
    """Root endpoint"""
    return {
        "message": f"Welcome to {settings.APP_NAME}",
        "version": settings.VERSION,
        "graphql_endpoint": "/graphql",
        "rest_api_docs": "/docs",
        "graphiql_endpoint": "/graphql (GET request for GraphiQL interface)"
    }


# GraphQL endpoint - Use add_route to avoid 307 redirects
graphql_app = GraphQLApp(
    schema=schema,
    on_get=make_graphiql_handler()  # Enable GraphiQL interface
)

app.add_route("/graphql", graphql_app)
app.add_route("/graphql/", graphql_app)  # Also handle trailing slash


# Startup event
@app.on_event("startup")
async def startup_event():
    """Initialize connections on startup"""
    neo4j_driver.verify_connectivity()
    try:
        await asyncio.to_thread(neo4j_driver.ensure_indexes)
    except Exception:
        logger.exception("Failed to create Neo4j indexes — continuing startup")

# Shutdown event
@app.on_event("shutdown")
async def shutdown_event():
    """Cleanup on shutdown"""
    await close_redis()
    neo4j_driver.close()


# Combined ASGI app (FastAPI + Socket.IO)
combined_app = socketio.ASGIApp(
    sio,
    other_asgi_app=app,
    socketio_path=settings.SOCKETIO_PATH,
)


def main():
    """Run the application"""
    uvicorn.run(
        "app.main:combined_app",
        host=settings.HOST,
        port=settings.PORT,
        reload=settings.DEBUG,
        log_level="error",
    )


if __name__ == "__main__":
    main()
# uvicorn reloaded
