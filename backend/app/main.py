from fastapi import FastAPI
from app.routes import router

app = FastAPI(title="AV8 Backend")
app.include_router(router)