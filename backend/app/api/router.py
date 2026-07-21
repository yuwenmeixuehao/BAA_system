from fastapi import APIRouter

from app.api.admin import router as admin_router
from app.api.attachments import router as attachments_router
from app.api.chat import router as chat_router
from app.api.health import router as health_router
from app.api.me import router as me_router
from app.api.results import router as results_router
from app.api.tasks import router as tasks_router
from app.api.websocket import router as websocket_router

api_router = APIRouter()
api_router.include_router(admin_router)
api_router.include_router(attachments_router)
api_router.include_router(chat_router)
api_router.include_router(health_router)
api_router.include_router(me_router)
api_router.include_router(results_router)
api_router.include_router(tasks_router)
api_router.include_router(websocket_router)
