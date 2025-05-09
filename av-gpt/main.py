from fastapi import FastAPI, HTTPException, UploadFile, File, BackgroundTasks
from pydantic import BaseModel
from typing import List, Dict, Optional
from openai import OpenAI  # Import the new OpenAI client
import os
import json
import threading
import fitz  # PyMuPDF for PDF text extraction
import pandas as pd
from fpdf import FPDF  # For creating PDF exports
import uuid
from fastapi.responses import FileResponse

# Initialize OpenAI client with API key from environment variable
client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

TAXONOMY_PATH = "taxonomy_db_extended.json"
taxonomy_lock = threading.Lock()  # Prevent race conditions when updating taxonomy

# Initialize FastAPI app
app = FastAPI(title="GPT AV Interpreter", version="v0.3")

# Request and response models for the API
class AVInterpretRequest(BaseModel):
    ocr_text: str
    taxonomy: Optional[Dict[str, Dict[str, str]]] = None
    request_pull_sheet: Optional[bool] = False
    request_bom: Optional[bool] = False

class AVInterpretResponse(BaseModel):
    summary: str
    devices: List[str]
    signal_flow: List[str]
    notes: List[str]
    new_taxonomy_entries: Dict[str, Dict[str, str]]
    cable_pull_sheet: Optional[str] = None
    reflected_bom: Optional[str] = None

# Load taxonomy database from file
def load_taxonomy() -> Dict:
    if os.path.exists(TAXONOMY_PATH):
        with open(TAXONOMY_PATH, "r") as f:
            return json.load(f)
    return {"devices": {}, "symbols": {}, "abbreviations": {}, "wire_labels": {}}

# Merge new entries into the taxonomy file
def update_taxonomy(new_entries: Dict[str, Dict[str, str]]):
    with taxonomy_lock:
        taxonomy = load_taxonomy()
        updated = False
        for section, entries in new_entries.items():
            if section not in taxonomy:
                taxonomy[section] = {}
            for k, v in entries.items():
                if k not in taxonomy[section]:
                    taxonomy[section][k] = v
                    updated = True
        if updated:
            with open(TAXONOMY_PATH, "w") as f:
                json.dump(taxonomy, f, indent=2)

# Construct a prompt for the GPT model using OCR and optional taxonomy
def build_prompt(ocr_text: str, taxonomy: Optional[Dict[str, Dict[str, str]]] = None, include_extras=False) -> str:
    base_prompt = f"""
You are an AV systems expert. Analyze the following OCR’d plan text and extract structured information.

Return your answer in the following JSON structure:
{{
  "summary": "...",
  "devices": [...],
  "signal_flow": [...],
  "notes": [...],
  "new_taxonomy_entries": {{
    "devices": {{...}},
    "symbols": {{...}},
    "abbreviations": {{...}},
    "wire_labels": {{...}}
  }}
}}

Use the following references:
"""
    if taxonomy:
        for category, values in taxonomy.items():
            base_prompt += f"\n{category.upper()}\n" + json.dumps(values, indent=2)

    base_prompt += f"\n\nOCR TEXT:\n{ocr_text}\n"

    if include_extras:
        base_prompt += (
            "\nAlso, generate a cable pull sheet (basic format), a reflected Bill of Materials (BOM), a detailed system summary, and a system verification list."
            "\nReturn each as separate text strings inside 'cable_pull_sheet', 'reflected_bom', 'detailed_summary', and 'system_verification'."
        )
    return base_prompt

# Call the OpenAI API and return parsed JSON
def call_openai(prompt: str) -> Dict:
    try:
        response = client.chat.completions.create(
            model="gpt-3.5-turbo",
            messages=[{"role": "user", "content": prompt}],
            temperature=0.3
        )
        content = response.choices[0].message.content
        return json.loads(content)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# Extract all text from a given PDF file
def extract_text_from_pdf(path: str) -> str:
    doc = fitz.open(path)
    text = ""
    for page in doc:
        text += page.get_text()
    return text

# Save a body of text as a simple PDF
def export_to_pdf(title: str, body: str, filename: str):
    pdf = FPDF()
    pdf.add_page()
    pdf.set_font("Arial", size=12)
    pdf.multi_cell(0, 10, f"{title}\n\n{body}")
    pdf.output(filename)

# Save text as CSV with a header
def export_to_csv(data: str, filename: str):
    with open(filename, "w") as f:
        f.write("Section,Line\n")
        for line in data.split("\n"):
            f.write(f"Data,{line.strip()}\n")

# Upload endpoint: handles PDF upload, OCR, GPT call, and generates reports
@app.post("/upload", response_model=AVInterpretResponse)
def upload_pdf(file: UploadFile = File(...)):
    filename = file.filename
    path = f"/tmp/{filename}"

    # Save uploaded PDF to disk
    with open(path, "wb") as f:
        f.write(file.file.read())

    # OCR processing
    ocr_text = extract_text_from_pdf(path)

    # Prepare request object for /interpret
    request = AVInterpretRequest(
        ocr_text=ocr_text,
        request_pull_sheet=True,
        request_bom=True
    )
    response = interpret_plan(request)

    # Generate PDF and CSV outputs
    export_to_pdf("Cable Pull Sheet", response.cable_pull_sheet or "None", f"/tmp/{filename}_pullsheet.pdf")
    export_to_pdf("Reflected BOM", response.reflected_bom or "None", f"/tmp/{filename}_bom.pdf")
    export_to_pdf("System Summary", response.summary, f"/tmp/{filename}_summary.pdf")
    export_to_pdf("System Verification", "\n".join(response.notes), f"/tmp/{filename}_verification.pdf")
    export_to_csv(response.cable_pull_sheet or "", f"/tmp/{filename}_pullsheet.csv")
    export_to_csv(response.reflected_bom or "", f"/tmp/{filename}_bom.csv")

    return response

# Allow frontend or Swagger to download generated files
@app.get("/files/{filename}")
def get_file(filename: str):
    file_path = f"/tmp/{filename}"
    if os.path.exists(file_path):
        return FileResponse(file_path)
    else:
        raise HTTPException(status_code=404, detail="File not found")

# GPT-powered plan interpretation endpoint
@app.post("/interpret", response_model=AVInterpretResponse, include_in_schema=False)
def interpret_plan(request: AVInterpretRequest):
    base_taxonomy = request.taxonomy if request.taxonomy is not None else load_taxonomy()
    prompt = build_prompt(
        ocr_text=request.ocr_text,
        taxonomy=base_taxonomy,
        include_extras=request.request_pull_sheet or request.request_bom
    )
    result = call_openai(prompt)

    update_taxonomy(result.get("new_taxonomy_entries", {}))

    return AVInterpretResponse(
        summary=result.get("summary", ""),
        devices=result.get("devices", []),
        signal_flow=result.get("signal_flow", []),
        notes=result.get("notes", []),
        new_taxonomy_entries=result.get("new_taxonomy_entries", {}),
        cable_pull_sheet=result.get("cable_pull_sheet"),
        reflected_bom=result.get("reflected_bom")
    )
