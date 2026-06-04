from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from database import init_db
from routes.notes import router as notes_router
from routes.calendar import router as calendar_router
from routes.push import router as push_router
from services.reminder_scheduler import start_scheduler, stop_scheduler

app = FastAPI(title="Assistant API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.on_event("startup")
def startup():
    init_db()
    start_scheduler()


@app.on_event("shutdown")
def shutdown():
    stop_scheduler()


app.include_router(notes_router)
app.include_router(calendar_router)
app.include_router(push_router)


@app.get("/health")
def health():
    return {"status": "ok"}
