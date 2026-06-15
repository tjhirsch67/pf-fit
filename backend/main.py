"""PF Coach API — FastAPI application entry point.

Schema is owned by Alembic (`alembic upgrade head`, run on boot via the Procfile), not
`create_all`. Routers are registered below; the data plane is JWT-bearer authenticated.
"""

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware

from config import settings
from routers import (
    auth_router,
    clubs,
    intake,
    me,
    programs,
    progress_router,
    sessions,
)

app = FastAPI(title="PF Coach API", version="0.1.0")

# Bearer tokens travel in the Authorization header, so credentialed CORS isn't needed.
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins_list,
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.middleware("http")
async def security_headers(request: Request, call_next):
    response = await call_next(request)
    response.headers.setdefault("X-Content-Type-Options", "nosniff")
    response.headers.setdefault("X-Frame-Options", "DENY")
    response.headers.setdefault("Referrer-Policy", "no-referrer")
    response.headers.setdefault("Content-Security-Policy", "default-src 'none'")
    response.headers.setdefault("Permissions-Policy", "geolocation=(), microphone=(), camera=()")
    return response


app.include_router(auth_router.router)
app.include_router(me.router)
app.include_router(clubs.router)
app.include_router(intake.router)
app.include_router(programs.router)
app.include_router(sessions.router)
app.include_router(progress_router.router)


@app.get("/")
def root():
    return {"status": "PF Coach API is online", "version": app.version}


@app.get("/health")
def health():
    return {"status": "ok"}
