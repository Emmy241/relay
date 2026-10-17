from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.db import Base, engine
from app import models  # noqa
from app.routers import webhooks as webhooks_router
from app.routers import events as events_router
from app.routers import admin as admin_router


Base.metadata.create_all(bind=engine)

app = FastAPI(title="Relay")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(webhooks_router.router)
app.include_router(events_router.router)
app.include_router(admin_router.router)


@app.get("/health")
def health():
    return {"status": "ok"}
