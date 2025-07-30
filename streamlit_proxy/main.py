"""
Main entry point for the Streamlit FastAPI Proxy application.
"""

import signal
import sys
import atexit
import asyncio
import logging
from contextlib import asynccontextmanager
from fastapi import FastAPI, Request
from fastapi.responses import RedirectResponse
from starlette.middleware.cors import CORSMiddleware
from .proxy import router as proxy_router, cleanup_websocket_proxy
from .app_manager import manager_router
from .services import app_service

# Set up logging
logger = logging.getLogger(__name__)

async def cleanup_running_apps():
    """Clean up all running Streamlit processes."""
    try:
        print("\n🧹 Cleaning up running Streamlit apps...")
        await app_service.cleanup_all()
        await app_service.close_http_client()
        await cleanup_websocket_proxy()
        print("✅ Cleanup completed!")
    except Exception as e:
        logger.error(f"Error during cleanup: {e}")

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Handle application startup and shutdown."""
    # Startup
    logger.info("Starting Streamlit FastAPI Proxy...")
    yield
    # Shutdown
    logger.info("Shutting down Streamlit FastAPI Proxy...")
    try:
        await cleanup_running_apps()
    except asyncio.CancelledError:
        logger.debug("Cleanup cancelled during shutdown")
        raise
    except Exception as e:
        logger.error(f"Error during shutdown cleanup: {e}")

def create_app() -> FastAPI:
    """Create and configure the FastAPI application."""
    
    app = FastAPI(
        title="Streamlit FastAPI Proxy",
        description="A proxy server for managing multiple Streamlit applications",
        version="0.1.0",
        lifespan=lifespan
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    app.include_router(manager_router, prefix="/apps", tags=["App Management"])
    app.include_router(proxy_router, prefix="/apps", tags=["Proxy"])

    # Add redirect for apps without trailing slash
    @app.get("/apps/{slug}")
    async def redirect_to_app(slug: str):
        return RedirectResponse(url=f"/apps/{slug}/", status_code=301)

    return app

def main():
    """Main entry point for running the application."""
    app = create_app()
    return app

if __name__ == "__main__":
    import uvicorn
    app = main()
    uvicorn.run(app, host="0.0.0.0", port=8000)

# Export the app for uvicorn
app = create_app()
