from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from app.api.deps import require_auth

router = APIRouter()

@router.get("/")
def root():
    return RedirectResponse("/ui")

@router.get("/ui", response_class=HTMLResponse)
def ui_page(request: Request, _=Depends(require_auth)):
    return HTMLResponse("<!doctype html><html><body><h2>Dashboard</h2><p>Login OK. UI folgt…</p></body></html>")
