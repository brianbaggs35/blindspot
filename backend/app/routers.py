"""Every router the app serves. The tests walk this list to check each route has a policy, so a
router that is added to the app must be added here (it is the only place the app reads from)."""

from fastapi import APIRouter

from app.ai.connect import router as connect_router
from app.ai.routes import router as ai_router
from app.auth.audit_routes import router as audit_router
from app.auth.passkey_routes import router as passkey_router
from app.auth.routes import router as auth_router
from app.auth.users import router as users_router
from app.health import router as health_router
from app.methodology.routes import router as methodology_router
from app.pentests.checklist import router as checklist_router
from app.pentests.gate import router as gate_router
from app.pentests.routes import router as pentests_router
from app.terms.routes import router as terms_router
from app.tools.routes import router as tools_router

ROUTERS: list[APIRouter] = [
    health_router,
    auth_router,
    passkey_router,
    users_router,
    audit_router,
    ai_router,
    connect_router,
    methodology_router,
    gate_router,
    checklist_router,
    pentests_router,
    terms_router,
    tools_router,
]
