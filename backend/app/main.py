import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from .config import check_runtime_settings
from .db import init_db
from .routers import activity, auth, graph, groups, hybrid, meta

log = logging.getLogger("shadowtrace")


@asynccontextmanager
async def lifespan(_app: FastAPI):
    check_runtime_settings()
    init_db()
    yield


# Interactive docs are disabled: the API is internal to the web app.
app = FastAPI(title="ShadowTrace API", version="1.0.0", lifespan=lifespan, docs_url=None, redoc_url=None, openapi_url=None)


@app.middleware("http")
async def security_headers(request: Request, call_next):
    # State-changing requests must be JSON (blocks simple cross-site form posts in addition to SameSite).
    if request.method in ("POST", "PUT", "DELETE", "PATCH") and request.url.path.startswith("/api/"):
        ctype = request.headers.get("content-type", "")
        has_body = request.headers.get("content-length", "0") not in ("", "0")
        if has_body and not ctype.startswith("application/json"):
            return JSONResponse({"detail": "Content-Type must be application/json"}, status_code=415)
        if request.headers.get("x-requested-with") != "shadowtrace":
            return JSONResponse({"detail": "Missing X-Requested-With header"}, status_code=403)
    response = await call_next(request)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["Referrer-Policy"] = "same-origin"
    response.headers["X-Frame-Options"] = "DENY"
    return response


for r in (auth.router, groups.router, graph.router, activity.router, hybrid.router, meta.router):
    app.include_router(r)
