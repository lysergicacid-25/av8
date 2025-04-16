from fastapi import APIRouter, File, UploadFile
from fastapi.responses import JSONResponse
from app.parser import analyze_plan

router = APIRouter()

@router.post("/api/analyze")
async def analyze(file: UploadFile = File(...)):
    content = await file.read()
    result = analyze_plan(content, filename=file.filename)
    return JSONResponse(content=result)