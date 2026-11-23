"""Every router the app serves. The tests walk this list to check each route has a policy, so a
router that is added to the app must be added here (it is the only place the app reads from)."""

from fastapi import APIRouter

from app.auth.audit_routes import router as audit_router
from app.auth.passkey_routes import router as passkey_router
from app.auth.routes import router as auth_router
from app.auth.users import router as users_router
from app.health import router as health_router

ROUTERS: list[APIRouter] = [health_router, auth_router, passkey_router, users_router, audit_router]
