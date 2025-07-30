import logging

from fastapi import APIRouter, HTTPException

from .models import AppConfig
from .services import app_service

logger = logging.getLogger(__name__)

manager_router = APIRouter()


@manager_router.get("/")
def list_apps():
    """List all registered apps with their status."""
    apps = []
    for app in app_service.registry.get_all():
        is_running = app_service.is_app_running(app.slug)

        status = "running" if is_running else "stopped"
        app_info = {
            "name": app.name,
            "slug": app.slug,
            "path": app.path,
            "desired_port": app.desired_port,
            "run_by_default": app.run_by_default,
            "status": status,
        }

        if is_running:
            port = app_service.get_app_port(app.slug)
            app_info["actual_port"] = port
            app_info["last_access"] = app_service.running[app.slug].get("last_access")
            app_info["external_process"] = app_service.running[app.slug].get(
                "external_process", False
            )
            if app_service.running[app.slug]["process"]:
                app_info["process_id"] = app_service.running[app.slug]["process"].pid

        apps.append(app_info)
    return apps


@manager_router.post("/register")
def register_app(app: AppConfig):
    if app_service.registry.find(app.slug):
        raise HTTPException(400, detail="App already registered")
    app.desired_port = app.desired_port or app_service._find_free_port()
    app_service.registry.register(app)
    return {"message": "App registered", "port": app.desired_port}


@manager_router.post("/{slug}/start")
async def start_app(slug: str):
    """Start a specific app, or reuse existing process if available."""
    app = app_service.registry.find(slug)
    if not app:
        raise HTTPException(404, detail="App not found")

    if app_service.is_app_running(slug):
        port = app_service.get_app_port(slug)
        return {
            "message": "Already running",
            "port": port,
            "external_process": app_service.running[slug].get(
                "external_process", False
            ),
        }

    try:
        port = await app_service.start_app(slug)
        return {
            "message": "Started",
            "port": port,
            "process_id": app_service.running[slug]["process"].pid,
            "external_process": False,
        }
    except Exception as e:
        raise HTTPException(500, detail=f"Failed to start app: {str(e)}")


@manager_router.post("/{slug}/stop")
async def stop_app(slug: str):
    if not app_service.is_app_running(slug):
        raise HTTPException(404, detail="Not running")

    try:
        await app_service.stop_app(slug)
        return {"message": "Stopped", "slug": slug}
    except Exception as e:
        raise HTTPException(500, detail=f"Failed to stop app: {str(e)}")


@manager_router.get("/{slug}/status")
def get_app_status(slug: str):
    """Get detailed status of a specific app."""
    app = app_service.registry.find(slug)
    if not app:
        raise HTTPException(404, detail="App not found")

    if app_service.is_app_running(slug):
        port = app_service.get_app_port(slug)
        return {
            "slug": slug,
            "status": "running",
            "port": port,
            "last_access": app_service.running[slug].get("last_access"),
            "process_id": app_service.running[slug]["process"].pid,
        }
    else:
        return {"slug": slug, "status": "stopped"}


@manager_router.post("/cleanup")
async def cleanup_all_apps():
    """Stop and cleanup all running apps."""
    await app_service.cleanup_all()

    return {"message": "Cleanup completed", "total_stopped": len(app_service.running)}
