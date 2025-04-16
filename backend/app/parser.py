from app.gpt_interpreter import interpret
from app.utils import extract_text_from_pdf

def analyze_plan(file_bytes: bytes, filename: str):
    text = extract_text_from_pdf(file_bytes)
    result = interpret(text, filename)
    return result