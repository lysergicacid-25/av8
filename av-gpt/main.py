from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from typing import List, Dict, Optional
import openai
import os
import json
import threading

# Load API key from environment variable or Railway secrets
oai_key = os.getenv("OPENAI_API_KEY")
if not oai_key:
    raise EnvironmentError("OPENAI_API_KEY not set")

openai.api_key = oai_key

TAXONOMY_PATH = "taxonomy_db.json"
taxonomy_lock = threading.Lock()

app = FastAPI(title="GPT AV Interpreter", version="v0.1")

# ----------- Request and Response Models -----------
class AVInterpretRequest(BaseModel):
    ocr_text: str
    taxonomy: Optional[Dict[str, str]] = None
    request_pull_sheet: Optional[bool] = False
    request_bom: Optional[bool] = False

class AVInterpretResponse(BaseModel):
    summary: str
    devices: List[str]
    signal_flow: List[str]
    notes: List[str]
    new_taxonomy_entries: Dict[str, str]
    cable_pull_sheet: Optional[str] = None
    reflected_bom: Optional[str] = None

# ----------- Taxonomy Management -----------
def load_taxonomy() -> Dict:
    if os.path.exists(TAXONOMY_PATH):
        with open(TAXONOMY_PATH, "r") as f:
            return json.load(f)
    return {}

def update_taxonomy(new_entries: Dict[str, str]):
    with taxonomy_lock:
        taxonomy = load_taxonomy()
        updated = False
        for k, v in new_entries.items():
            if k not in taxonomy.get("devices", {}):
                taxonomy.setdefault("devices", {})[k] = v
                updated = True
        if updated:
            with open(TAXONOMY_PATH, "w") as f:
                json.dump(taxonomy, f, indent=2)

# ----------- Prompt Builder -----------
def build_prompt(ocr_text: str, taxonomy: Optional[Dict[str, str]] = None, include_extras=False) -> str:
    base_prompt = f"""
You are an AV systems expert. Analyze the following OCR’d plan text and extract structured information.

Return your answer in the following JSON structure:
{{
  "summary": "...",
  "devices": [...],
  "signal_flow": [...],
  "notes": [...],
  "new_taxonomy_entries": {{...}}
}}

If possible, guess at unknown device types or abbreviations and suggest classifications.

OCR TEXT:
{ocr_text}
"""
    if include_extras:
        base_prompt += (
            "\nAlso, generate a cable pull sheet (basic format) and a reflected Bill of Materials (BOM) based on the device list."
            "\nInclude these as string fields 'cable_pull_sheet' and 'reflected_bom' in your final JSON output."
        )
    if taxonomy:
        base_prompt += "\n\nKnown taxonomy for reference:\n" + json.dumps(taxonomy, indent=2)
    return base_prompt

# ----------- Live GPT Call -----------
def call_openai(prompt: str) -> Dict:
    try:
        response = openai.ChatCompletion.create(
            model="gpt-4",
            messages=[{"role": "user", "content": prompt}],
            temperature=0.3
        )
        content = response["choices"][0]["message"]["content"]
        return json.loads(content)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# ----------- API Route -----------
@app.post("/interpret", response_model=AVInterpretResponse)
def interpret_plan(request: AVInterpretRequest):
    base_taxonomy = request.taxonomy if request.taxonomy is not None else load_taxonomy()
    prompt = build_prompt(
        ocr_text=request.ocr_text,
        taxonomy=base_taxonomy,
        include_extras=request.request_pull_sheet or request.request_bom
    )
    result = call_openai(prompt)

    # Persist new taxonomy additions
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


