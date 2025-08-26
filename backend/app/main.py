from fastapi import FastAPI, Request
EXEMPT_PREFIXES = ("/health","/login","/api/login","/openapi.json","/docs","/redoc","/static","/favicon.ico")
from fastapi.responses import RedirectResponse
from starlette.middleware.sessions import SessionMiddleware

from app.core.config import get_settings
from app.api.routers.auth import router as auth_router
from app.api.routers.ui import router as ui_router
from app.db.base import Base
from app.db.session import engine

# DB-Tabellen sicherstellen (nur für Users; Reports bleiben Alembic-gesteuert)
Base.metadata.create_all(bind=engine)

settings = get_settings()
app = FastAPI(title="Seller Control", docs_url=None, redoc_url=None)
app.include_router(auth_router)

# Sessions (vor Routern/Middleware)
app.add_middleware(SessionMiddleware, secret_key=settings.SESSION_SECRET, same_site="lax", https_only=False)

# Router registrieren
app.include_router(ui_router)

# Fallback: Unauth → Login
@app.middleware("http")
async def force_auth_on_html(request: Request, call_next):
    # /login & /api/* exempt
    path = request.scope.get("path","")
    if path.startswith("/api") or path.startswith("/login"):
        return await call_next(request)
    # HTML wants UI; if not logged in redirect to /login
    if "text/html" in request.headers.get("accept","") and not (request.scope.get("session") or {}).get("uid"):
        return RedirectResponse("/login")
    return await call_next(request)
