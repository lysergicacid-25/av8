from fastapi import FastAPI
from app.routes import router

app = FastAPI(title="AVIATE Backend")
app.include_router(router)