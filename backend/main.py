import os
import json
import io
from typing import TypedDict, Literal

import pypdf
from fastapi import FastAPI, UploadFile, File, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from groq import Groq

# ----------------------------------------------------------------------
# FastAPI app & CORS
# ----------------------------------------------------------------------
app = FastAPI()
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# ----------------------------------------------------------------------
# Groq client – **never hard‑code the key**.  Use an env var instead.
# ----------------------------------------------------------------------
GROQ_API_KEY = os.getenv("GROQ_API_KEY")
if not GROQ_API_KEY:
    print("Please add GROQ_API_KEY")
    raise RuntimeError("❗️ Set the GROQ_API_KEY environment variable before starting the server")

client = Groq(api_key=GROQ_API_KEY)

# ----------------------------------------------------------------------
# Types for a little runtime validation (helps catch malformed LLM output)
# ----------------------------------------------------------------------
class Address(TypedDict, total=False):
    street: str
    city: str
    state: str
    zip: str

class ExtractedInfo(TypedDict, total=False):
    name: str
    email: str
    phone: str
    address: Address

def _validate_extracted(data: dict) -> ExtractedInfo:
    """
    Very lightweight validation – we only check that the expected keys exist
    and that they are strings (or a dict for address).  If something is missing
    we replace it with "N/A".
    """
    def _as_str(value: any) -> str:
        return value if isinstance(value, str) else "N/A"

    address = data.get("address", {})
    if not isinstance(address, dict):
        address = {}

    return {
        "name":    _as_str(data.get("name")),
        "email":   _as_str(data.get("email")),
        "phone":   _as_str(data.get("phone")),
        "address": {
            "street": _as_str(address.get("street")),
            "city":   _as_str(address.get("city")),
            "state":  _as_str(address.get("state")),
            "zip":    _as_str(address.get("zip")),
        },
    }

# ----------------------------------------------------------------------
# Helper: extract plain text from a PDF (fallback to a simple OCR if needed)
# ----------------------------------------------------------------------
def _pdf_to_text(pdf_bytes: bytes) -> str:
    """
    Returns concatenated text of every page.  If a page fails to extract
    (e.g. scanned image), we simply skip it – the LLM will still try its best.
    """
    reader = pypdf.PdfReader(io.BytesIO(pdf_bytes))
    all_text = []
    for i, page in enumerate(reader.pages):
        try:
            page_text = page.extract_text()
            if page_text:
                all_text.append(page_text)
        except Exception as exc:
            # Log internally; FastAPI will still return a response.
            print(f"[WARN] Could not extract text from page {i}: {exc}")
    return "\n".join(all_text)


# ----------------------------------------------------------------------
# POST /extract – now also returns address
# ----------------------------------------------------------------------
@app.post("/extract")
async def extract_data(file: UploadFile = File(...)):
    # ------------------------------------------------------------------
    # 1️⃣ Basic file validation
    # ------------------------------------------------------------------
    if file.content_type != "application/pdf":
        raise HTTPException(status_code=400, detail="Only PDF files are supported.")

    pdf_bytes = await file.read()
    if not pdf_bytes:
        raise HTTPException(status_code=400, detail="Uploaded file is empty.")

    # ------------------------------------------------------------------
    # 2️⃣ Convert PDF → plain text
    # ------------------------------------------------------------------
    text = _pdf_to_text(pdf_bytes)
    if not text.strip():
        raise HTTPException(
            status_code=422,
            detail="Could not extract any readable text from the PDF."
        )

    # ------------------------------------------------------------------
    # 3️⃣ Prompt Groq for structured extraction (name, email, phone, address)
    # ------------------------------------------------------------------
    system_prompt = (
        "You are a data‑extraction assistant. "
        "Read the provided text and extract the following fields:\n"
        "- name (full name)\n"
        "- email\n"
        "- phone (any international format)\n"
        "- address (break it down into street, city, state, zip)\n\n"
        "Return **only** a JSON object with exactly these keys:\n"
        "{\n"
        '  "name": "...",\n'
        '  "email": "...",\n'
        '  "phone": "...",\n'
        '  "address": {\n'
        '    "street": "...",\n'
        '    "city": "...",\n'
        '    "state": "...",\n'
        '    "zip": "..." \n'
        "  }\n"
        "}\n"
        "If a piece of information is missing, use the string \"N/A\" for that field."
    )

    try:
        completion = client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user",   "content": f"Extract details from this text:\n\n{text}"}
            ],
            # Force the model to output valid JSON – Groq respects the OpenAI style
            response_format={"type": "json_object"},
            temperature=0.0,          # deterministic for extraction tasks
            max_tokens=500            # plenty for a tiny JSON payload
        )
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"LLM request failed: {exc}")

    # ------------------------------------------------------------------
    # 4️⃣ Parse the JSON response
    # ------------------------------------------------------------------
    try:
        raw_json = completion.choices[0].message.content
        parsed = json.loads(raw_json)
    except Exception as exc:
        raise HTTPException(
            status_code=502,
            detail=f"Unable to parse LLM response as JSON: {exc}"
        )

    # ------------------------------------------------------------------
    # 5️⃣ Light validation & normalisation
    # ------------------------------------------------------------------
    extracted = _validate_extracted(parsed)

    return extracted