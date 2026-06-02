import os
import json
import io
import uuid
import shutil
from pathlib import Path
from typing import Any, Dict, List, Optional
from datetime import datetime, timedelta
from contextlib import asynccontextmanager

import jwt
from jwt.exceptions import PyJWTError
import pypdf
import psycopg
from passlib.context import CryptContext
from fastapi import FastAPI, UploadFile, File, HTTPException, Form, Header, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from pydantic import BaseModel, EmailStr
from dotenv import load_dotenv
from sentence_transformers import SentenceTransformer
from sentence_transformers.util import cos_sim
from qdrant_client import QdrantClient
from qdrant_client.models import Distance, VectorParams, PointStruct, Filter, FieldCondition, MatchValue
from psycopg import sql

# Load environment variables
load_dotenv()

# ----------------------------------------------------------------------
# Configuration
# ----------------------------------------------------------------------
GROQ_API_KEY = os.getenv("GROQ_API_KEY")
EXPLANATION_THRESHOLD = float(os.getenv("EXPLANATION_THRESHOLD", "0.6"))
MAX_SCALE = int(os.getenv("MAX_SCALE", "200"))
QDRANT_PATH = os.getenv("QDRANT_PATH", "./qdrant_storage")

# Groq client (optional - only for explanations)
groq_client = None
if GROQ_API_KEY:
    from groq import Groq
    groq_client = Groq(api_key=GROQ_API_KEY)
    print("✓ Groq API configured for explanations")
else:
    print("⚠ Groq API key not found - explanations will be disabled")

# ----------------------------------------------------------------------
# Global state
# ----------------------------------------------------------------------
embedding_model: Optional[SentenceTransformer] = None
qdrant_client: Optional[QdrantClient] = None
postgres_conn: Optional[psycopg.Connection] = None
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
SECRET_KEY = os.getenv("SECRET_KEY")
JWT_ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = int(os.getenv("ACCESS_TOKEN_EXPIRE_MINUTES", "60"))

class AuthPayload(BaseModel):
    email: EmailStr
    password: str
    role: Optional[str] = None


def get_password_hash(password: str) -> str:
    return pwd_context.hash(password)


def verify_password(plain_password: str, hashed_password: str) -> bool:
    return pwd_context.verify(plain_password, hashed_password)


def create_access_token(data: Dict[str, Any], expires_delta: Optional[timedelta] = None) -> str:
    to_encode = data.copy()
    expire = datetime.utcnow() + (expires_delta or timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES))
    to_encode.update({"exp": expire})
    return jwt.encode(to_encode, SECRET_KEY, algorithm=JWT_ALGORITHM)


def decode_access_token(token: str) -> Dict[str, Any]:
    try:
        return jwt.decode(token, SECRET_KEY, algorithms=[JWT_ALGORITHM])
    except PyJWTError as exc:
        raise HTTPException(status_code=401, detail="Invalid or expired token") from exc


def auth_required(request: Request) -> Dict[str, Any]:
    auth_header = request.headers.get("Authorization")
    if not auth_header or not auth_header.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing authorization header")

    token = auth_header.split(" ", 1)[1]
    payload = decode_access_token(token)
    if "sub" not in payload:
        raise HTTPException(status_code=401, detail="Invalid token payload")
    return payload


def get_token_payload(request: Request) -> Dict[str, Any]:
    auth_header = request.headers.get("Authorization")
    if not auth_header or not auth_header.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing authorization header")

    token = auth_header.split(" ", 1)[1]
    payload = decode_access_token(token)
    if "sub" not in payload:
        raise HTTPException(status_code=401, detail="Invalid token payload")
    return payload


def require_role(request: Request, allowed_roles: List[str]) -> Dict[str, Any]:
    payload = get_token_payload(request)
    if payload.get("is_admin"):
        return payload

    role = payload.get("role") or "user"
    if role not in allowed_roles:
        raise HTTPException(status_code=403, detail="Forbidden: insufficient permissions")
    return payload


def get_user_by_email(email: str) -> Optional[Dict[str, Any]]:
    global postgres_conn
    if postgres_conn is None:
        return None

    with postgres_conn.cursor() as cur:
        cur.execute("SELECT id, email, password_hash, is_admin, role, created_at FROM users WHERE email = %s", (email,))
        row = cur.fetchone()
        if not row:
            return None
        return {
            "id": row[0],
            "email": row[1],
            "password_hash": row[2],
            "is_admin": row[3],
            "role": row[4],
            "created_at": row[5]
        }


def create_user(email: str, password: str, role: str = "user", is_admin: bool = False) -> Dict[str, Any]:
    global postgres_conn
    if postgres_conn is None:
        raise RuntimeError("Postgres connection is not initialized")

    hashed_password = get_password_hash(password)
    with postgres_conn.cursor() as cur:
        cur.execute(
            "INSERT INTO users (email, password_hash, role, is_admin) VALUES (%s, %s, %s, %s) RETURNING id, created_at",
            (email, hashed_password, role, is_admin)
        )
        row = cur.fetchone()
        postgres_conn.commit()
        return {
            "id": row[0],
            "email": email,
            "role": role,
            "is_admin": is_admin,
            "created_at": row[1]
        }


def initialize_postgres() -> None:
    global postgres_conn, SECRET_KEY

    if not SECRET_KEY:
        raise RuntimeError("SECRET_KEY environment variable must be set")

    postgres_host = os.getenv("POSTGRES_HOST", "localhost")
    postgres_port = int(os.getenv("POSTGRES_PORT", "5432"))
    postgres_db = os.getenv("POSTGRES_DB", "resume_analyzer")
    postgres_user = os.getenv("POSTGRES_USER", "postgres")
    postgres_password = os.getenv("POSTGRES_PASSWORD", "")

    # Ensure the database exists
    with psycopg.connect(host=postgres_host, port=postgres_port, dbname="postgres", user=postgres_user, password=postgres_password, autocommit=True) as admin_conn:
        with admin_conn.cursor() as cur:
            cur.execute("SELECT 1 FROM pg_database WHERE datname = %s", (postgres_db,))
            if cur.fetchone() is None:
                cur.execute(sql.SQL("CREATE DATABASE {}") .format(sql.Identifier(postgres_db)))
                print(f"✓ Created Postgres database '{postgres_db}'")
            else:
                print(f"✓ Postgres database '{postgres_db}' exists")

    # Connect to the target database and ensure the users table exists
    postgres_conn = psycopg.connect(host=postgres_host, port=postgres_port, dbname=postgres_db, user=postgres_user, password=postgres_password, autocommit=True)
    with postgres_conn.cursor() as cur:
        cur.execute(
            "CREATE TABLE IF NOT EXISTS users ("
            "id SERIAL PRIMARY KEY, "
            "email TEXT UNIQUE NOT NULL, "
            "password_hash TEXT NOT NULL, "
            "role TEXT NOT NULL DEFAULT 'user', "
            "is_admin BOOLEAN NOT NULL DEFAULT FALSE, "
            "created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW()"
            ")"
        )
        cur.execute(
            "ALTER TABLE users ADD COLUMN IF NOT EXISTS role TEXT NOT NULL DEFAULT 'user'"
        )
        postgres_conn.commit()
        print("✓ Users table exists in Postgres")

        # Create default admin if missing
        admin_email = os.getenv("ADMIN_EMAIL")
        admin_password = os.getenv("ADMIN_PASSWORD")
        if admin_email and admin_password:
            cur.execute("SELECT 1 FROM users WHERE email = %s", (admin_email,))
            if cur.fetchone() is None:
                hashed_admin_password = get_password_hash(admin_password)
                cur.execute(
                    "INSERT INTO users (email, password_hash, role, is_admin) VALUES (%s, %s, %s, TRUE)",
                    (admin_email, hashed_admin_password, "admin")
                )
                postgres_conn.commit()
                print(f"✓ Default admin user created: {admin_email}")
            else:
                print(f"✓ Default admin user already exists: {admin_email}")
        else:
            print("⚠ ADMIN_EMAIL or ADMIN_PASSWORD is not set; default admin user was not created")

# ----------------------------------------------------------------------
# Lifespan event - Initialize embedding model and vector database
# ----------------------------------------------------------------------
@asynccontextmanager
async def lifespan(app: FastAPI):
    global embedding_model, qdrant_client
    
    print("🚀 Starting Resume Analyzer...")

    # Initialize Postgres and user auth storage
    print("🗄️  Checking Postgres connection and user database...")
    initialize_postgres()
    print("✓ Postgres auth initialization complete")
    
    # Create upload directories
    Path("./uploads/resumes").mkdir(parents=True, exist_ok=True)
    Path("./uploads/jobs").mkdir(parents=True, exist_ok=True)
    print("✓ Upload directories created")
    
    # Load embedding model (this will download ~80MB on first run)
    print("📦 Loading embedding model (all-MiniLM-L6-v2)...")
    embedding_model = SentenceTransformer('all-MiniLM-L6-v2')
    print("✓ Embedding model loaded")
    
    # Initialize Qdrant client with persistent storage
    print(f"💾 Initializing Qdrant database at {QDRANT_PATH}...")
    qdrant_client = QdrantClient(path=QDRANT_PATH)
    
    # Create collections if they don't exist
    collections = [c.name for c in qdrant_client.get_collections().collections]
    
    if "resumes" not in collections:
        qdrant_client.create_collection(
            collection_name="resumes",
            vectors_config=VectorParams(size=384, distance=Distance.COSINE)
        )
        print("✓ Created 'resumes' collection")
    else:
        print("✓ 'resumes' collection exists")
    
    if "job_descriptions" not in collections:
        qdrant_client.create_collection(
            collection_name="job_descriptions",
            vectors_config=VectorParams(size=384, distance=Distance.COSINE)
        )
        print("✓ Created 'job_descriptions' collection")
    else:
        print("✓ 'job_descriptions' collection exists")
    
    # Collection for user-added job descriptions (for job seeker workflow)
    if "user_job_descriptions" not in collections:
        qdrant_client.create_collection(
            collection_name="user_job_descriptions",
            vectors_config=VectorParams(size=384, distance=Distance.COSINE)
        )
        print("✓ Created 'user_job_descriptions' collection")
    else:
        print("✓ 'user_job_descriptions' collection exists")
    
    # Collection for storing analysis results (cached rankings/matches)
    if "analysis_results" not in collections:
        qdrant_client.create_collection(
            collection_name="analysis_results",
            vectors_config=VectorParams(size=384, distance=Distance.COSINE)
        )
        print("✓ Created 'analysis_results' collection")
    else:
        print("✓ 'analysis_results' collection exists")
    
    print("✅ Resume Analyzer ready!")
    
    yield  # Server runs here
    
    # Cleanup on shutdown (if needed)
    print("🔄 Shutting down Resume Analyzer...")

# ----------------------------------------------------------------------
# FastAPI app with lifespan
# ----------------------------------------------------------------------
app = FastAPI(
    title="Resume Analyzer API", 
    version="2.0.0",
    lifespan=lifespan
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.middleware("http")
async def auth_middleware(request: Request, call_next):
    # Allow CORS preflight and open auth routes without requiring a token.
    if request.method == "OPTIONS":
        return await call_next(request)

    open_paths = ["/api/auth/login", "/api/auth/register", "/"]
    if request.url.path.startswith("/api/") and request.url.path not in open_paths:
        auth_header = request.headers.get("Authorization")
        if not auth_header or not auth_header.startswith("Bearer "):
            return JSONResponse({"detail": "Missing authorization header"}, status_code=401)
        token = auth_header.split(" ", 1)[1]
        try:
            payload = decode_access_token(token)
            request.state.user = payload
        except HTTPException as exc:
            return JSONResponse({"detail": exc.detail}, status_code=exc.status_code)
    return await call_next(request)

# ----------------------------------------------------------------------
# Helper: extract plain text from a PDF
# ----------------------------------------------------------------------
def _pdf_to_text(pdf_bytes: bytes) -> str:
    """
    Returns concatenated text of every page. If a page fails to extract,
    we skip it and continue.
    """
    reader = pypdf.PdfReader(io.BytesIO(pdf_bytes))
    all_text = []
    for i, page in enumerate(reader.pages):
        try:
            page_text = page.extract_text()
            if page_text:
                all_text.append(page_text)
        except Exception as exc:
            print(f"[WARN] Could not extract text from page {i}: {exc}")
    return "\n".join(all_text)

# ----------------------------------------------------------------------
# Helper: Generate AI explanation using Groq (optional)
# ----------------------------------------------------------------------
def _generate_explanation(resume_text: str, job_description: str, score: float) -> Optional[str]:
    """
    Generate explanation for why a resume matches a job description.
    Returns None if Groq is not configured or score below threshold.
    """
    if not groq_client or score < EXPLANATION_THRESHOLD:
        return None
    
    try:
        system_prompt = (
            "You are an HR assistant. Explain why this resume matches the job description "
            "in 2-3 concise sentences. Focus on key skills, experience, and qualifications that align."
        )
        
        user_prompt = f"""Job Description:
{job_description[:1000]}

Resume Preview:
{resume_text[:1000]}

Match Score: {score:.1%}

Explain why this is a good match:"""
        
        completion = groq_client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt}
            ],
            temperature=0.3,
            max_tokens=200
        )
        
        return completion.choices[0].message.content.strip()
    except Exception as exc:
        print(f"[WARN] Failed to generate explanation: {exc}")
        return None

# ----------------------------------------------------------------------
# HR ENDPOINTS
# ----------------------------------------------------------------------

@app.post("/api/hr/jobs")
async def create_job(request: Request, name: str = Form(...), description: str = Form(...)):
    """Create a new job posting for HR use"""
    require_role(request, ["hr"])
    if not name or not description:
        raise HTTPException(status_code=400, detail="Job name and description are required")
    
    # Generate embedding for job description
    embedding = embedding_model.encode(description)
    
    # Create unique job ID
    job_id = str(uuid.uuid4())
    
    # Store in Qdrant
    qdrant_client.upsert(
        collection_name="job_descriptions",
        points=[
            PointStruct(
                id=job_id,
                vector=embedding.tolist(),
                payload={
                    "job_name": name,
                    "description_text": description,
                    "created_at": datetime.now().isoformat()
                }
            )
        ]
    )
    
    return {
        "job_id": job_id,
        "job_name": name,
        "message": "Job created successfully"
    }

@app.get("/api/hr/jobs")
async def list_jobs(request: Request):
    """List all job postings"""
    require_role(request, ["hr"])
    # Scroll through all jobs (Qdrant doesn't have a simple "get all" for large collections)
    jobs = []
    
    # Get all points from collection
    scroll_result = qdrant_client.scroll(
        collection_name="job_descriptions",
        limit=MAX_SCALE,
        with_payload=True,
        with_vectors=False
    )
    
    points = scroll_result[0]
    
    for point in points:
        # Count resumes for this job
        resume_count = qdrant_client.count(
            collection_name="resumes",
            count_filter=Filter(
                must=[
                    FieldCondition(
                        key="job_id",
                        match=MatchValue(value=point.id)
                    )
                ]
            )
        )
        
        jobs.append({
            "job_id": point.id,
            "job_name": point.payload.get("job_name"),
            "created_at": point.payload.get("created_at"),
            "resume_count": resume_count.count
        })
    
    return {"jobs": jobs}

@app.post("/api/auth/register")
async def register(auth: AuthPayload):
    if len(auth.password) < 6:
        raise HTTPException(status_code=400, detail="Password must be at least 6 characters long")
    if get_user_by_email(auth.email):
        raise HTTPException(status_code=400, detail="Email already registered")

    role = auth.role or "user"
    if role not in ["hr", "user"]:
        raise HTTPException(status_code=400, detail="Role must be either 'hr' or 'user'")

    create_user(auth.email, auth.password, role=role)
    return {"message": "User registered successfully"}

@app.post("/api/auth/login")
async def login(auth: AuthPayload):
    user = get_user_by_email(auth.email)
    if not user or not verify_password(auth.password, user["password_hash"]):
        raise HTTPException(status_code=401, detail="Invalid email or password")

    access_token = create_access_token({
        "sub": user["email"],
        "is_admin": user["is_admin"],
        "role": user["role"]
    })
    return {
        "access_token": access_token,
        "token_type": "bearer",
        "email": user["email"],
        "role": user["role"],
        "is_admin": user["is_admin"]
    }

@app.get("/api/auth/me")
async def me(authorization: Optional[str] = Header(None)):
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing authorization header")

    token = authorization.split(" ", 1)[1]
    payload = decode_access_token(token)
    return {
        "email": payload.get("sub"),
        "is_admin": payload.get("is_admin", False),
        "role": payload.get("role", "user")
    }

@app.post("/api/hr/jobs/{job_id}/resumes")
async def upload_resumes_for_job(request: Request, job_id: str, files: List[UploadFile] = File(...)):
    """Upload multiple resumes for a specific job posting"""
    require_role(request, ["hr"])
    # Verify job exists
    try:
        qdrant_client.retrieve(
            collection_name="job_descriptions",
            ids=[job_id]
        )
    except:
        raise HTTPException(status_code=404, detail="Job not found")
    
    uploaded_resumes = []
    
    for file in files:
        if file.content_type != "application/pdf":
            continue  # Skip non-PDF files
        
        # Read PDF
        pdf_bytes = await file.read()
        if not pdf_bytes:
            continue
        
        # Extract text
        text = _pdf_to_text(pdf_bytes)
        if not text.strip():
            continue
        
        # Generate embedding
        embedding = embedding_model.encode(text)
        
        # Create unique resume ID
        resume_id = str(uuid.uuid4())
        
        # Save PDF to filesystem
        pdf_path = f"./uploads/resumes/{resume_id}.pdf"
        with open(pdf_path, "wb") as f:
            f.write(pdf_bytes)
        
        # Store in Qdrant
        qdrant_client.upsert(
            collection_name="resumes",
            points=[
                PointStruct(
                    id=resume_id,
                    vector=embedding.tolist(),
                    payload={
                        "job_id": job_id,
                        "filename": file.filename,
                        "pdf_path": pdf_path,
                        "uploaded_at": datetime.now().isoformat(),
                        "text_preview": text[:500],
                        "user_uploaded": False
                    }
                )
            ]
        )
        
        uploaded_resumes.append({
            "resume_id": resume_id,
            "filename": file.filename
        })
    
    return {
        "uploaded": len(uploaded_resumes),
        "resumes": uploaded_resumes
    }

@app.post("/api/hr/jobs/{job_id}/rank")
async def rank_resumes_for_job(request: Request, job_id: str):
    """Rank all resumes for a specific job based on similarity"""
    require_role(request, ["hr"])
    # Get job description
    try:
        job_points = qdrant_client.retrieve(
            collection_name="job_descriptions",
            ids=[job_id],
            with_vectors=True
        )
        if not job_points:
            raise HTTPException(status_code=404, detail="Job not found")
        
        job_point = job_points[0]
        job_vector = job_point.vector
        job_description = job_point.payload.get("description_text", "")
    except Exception as exc:
        raise HTTPException(status_code=404, detail=f"Job not found: {exc}")
    
    # Search for all resumes with this job_id using query method
    try:
        search_results = qdrant_client.query_points(
            collection_name="resumes",
            query=job_vector,
            limit=MAX_SCALE,
            query_filter=Filter(
                must=[
                    FieldCondition(
                        key="job_id",
                        match=MatchValue(value=job_id)
                    )
                ]
            ),
            with_payload=True
        ).points
    except Exception as exc:
        # Fallback to scroll if query_points doesn't work
        print(f"Query points failed: {exc}, using scroll instead")
        scroll_result = qdrant_client.scroll(
            collection_name="resumes",
            scroll_filter=Filter(
                must=[
                    FieldCondition(
                        key="job_id",
                        match=MatchValue(value=job_id)
                    )
                ]
            ),
            limit=MAX_SCALE,
            with_payload=True,
            with_vectors=True
        )
        
        # Calculate similarity scores manually
        from numpy import dot
        from numpy.linalg import norm
        
        def cosine_similarity(a, b):
            return dot(a, b) / (norm(a) * norm(b))
        
        search_results = []
        for point in scroll_result[0]:
            score = cosine_similarity(job_vector, point.vector)
            search_results.append({
                "point": point,
                "score": float(score)
            })
        
        # Sort by score descending
        search_results.sort(key=lambda x: x["score"], reverse=True)
    
    # Build ranked results
    ranked_resumes = []
    for rank, result in enumerate(search_results, 1):
        if isinstance(result, dict):
            point = result["point"]
            score = result["score"]
        else:
            point = result
            score = getattr(result, 'score', 0.0)
        
        resume_text = point.payload.get("text_preview", "")
        
        # Generate explanation for top 3 high-scoring matches
        explanation = None
        if rank <= 3:
            explanation = _generate_explanation(resume_text, job_description, score)
        
        ranked_resumes.append({
            "resume_id": point.id,
            "filename": point.payload.get("filename"),
            "score": float(score),
            "rank": rank,
            "explanation": explanation
        })
    
    # Store analysis results for caching
    try:
        analysis_id = str(uuid.uuid4())
        qdrant_client.upsert(
            collection_name="analysis_results",
            points=[
                PointStruct(
                    id=analysis_id,
                    vector=[0] * 384,  # Placeholder vector
                    payload={
                        "job_id": job_id,
                        "result_type": "hr_ranking",
                        "results_json": json.dumps(ranked_resumes),
                        "timestamp": datetime.now().isoformat(),
                        "resume_count": len(ranked_resumes)
                    }
                )
            ]
        )
    except Exception as e:
        print(f"Warning: Could not save analysis results: {e}")
    
    return {"ranked_resumes": ranked_resumes}

@app.get("/api/hr/jobs/{job_id}")
async def get_job_details(request: Request, job_id: str):
    """Get job details including description and list of resumes"""
    require_role(request, ["hr"])
    try:
        # Get job info
        job_points = qdrant_client.retrieve(
            collection_name="job_descriptions",
            ids=[job_id]
        )
        if not job_points:
            raise HTTPException(status_code=404, detail="Job not found")
        
        job_point = job_points[0]
        
        # Get all resumes for this job
        scroll_result = qdrant_client.scroll(
            collection_name="resumes",
            scroll_filter=Filter(
                must=[
                    FieldCondition(
                        key="job_id",
                        match=MatchValue(value=job_id)
                    )
                ]
            ),
            limit=MAX_SCALE,
            with_payload=True,
            with_vectors=False
        )
        
        resumes = []
        for point in scroll_result[0]:
            resumes.append({
                "resume_id": point.id,
                "filename": point.payload.get("filename"),
                "uploaded_at": point.payload.get("uploaded_at")
            })
        
        return {
            "job_id": job_id,
            "job_name": job_point.payload.get("job_name"),
            "description": job_point.payload.get("description_text"),
            "created_at": job_point.payload.get("created_at"),
            "resumes": resumes,
            "resume_count": len(resumes)
        }
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Error fetching job details: {exc}")

@app.get("/api/hr/jobs/{job_id}/latest-ranking")
async def get_latest_ranking(request: Request, job_id: str):
    """Get the most recent cached ranking results for a job"""
    require_role(request, ["hr"])
    try:
        # Get all analysis results for this job, sorted by timestamp
        scroll_result = qdrant_client.scroll(
            collection_name="analysis_results",
            scroll_filter=Filter(
                must=[
                    FieldCondition(
                        key="job_id",
                        match=MatchValue(value=job_id)
                    ),
                    FieldCondition(
                        key="result_type",
                        match=MatchValue(value="hr_ranking")
                    )
                ]
            ),
            limit=10,
            with_vectors=False,
            with_payload=True
        )
        
        if not scroll_result[0]:
            return {"has_cached_results": False}
        
        # Sort by timestamp and get the most recent
        results = scroll_result[0]
        results.sort(key=lambda x: x.payload.get("timestamp", ""), reverse=True)
        latest = results[0]
        
        ranked_resumes = json.loads(latest.payload.get("results_json", "[]"))
        
        return {
            "has_cached_results": True,
            "timestamp": latest.payload.get("timestamp"),
            "resume_count": latest.payload.get("resume_count", 0),
            "ranked_resumes": ranked_resumes
        }
    except Exception as e:
        return {"has_cached_results": False, "error": str(e)}

# ----------------------------------------------------------------------
# USER ENDPOINTS
# ----------------------------------------------------------------------

@app.post("/api/user/resumes")
async def upload_user_resume(
    request: Request,
    file: UploadFile = File(...),
    resume_name: str = Form(...)
):
    """Upload a resume for a job seeker"""
    require_role(request, ["user"])
    if file.content_type != "application/pdf":
        raise HTTPException(status_code=400, detail="Only PDF files are supported")
    
    # Read PDF
    pdf_bytes = await file.read()
    if not pdf_bytes:
        raise HTTPException(status_code=400, detail="Uploaded file is empty")
    
    # Extract text
    text = _pdf_to_text(pdf_bytes)
    if not text.strip():
        raise HTTPException(
            status_code=422,
            detail="Could not extract any readable text from the PDF"
        )
    
    # Generate embedding
    embedding = embedding_model.encode(text)
    
    # Create unique resume ID
    resume_id = str(uuid.uuid4())
    
    # Save PDF to filesystem
    pdf_path = f"./uploads/resumes/{resume_id}.pdf"
    with open(pdf_path, "wb") as f:
        f.write(pdf_bytes)
    
    # Store in Qdrant
    qdrant_client.upsert(
        collection_name="resumes",
        points=[
            PointStruct(
                id=resume_id,
                vector=embedding.tolist(),
                payload={
                    "job_id": None,
                    "user_uploaded": True,
                    "resume_name": resume_name,
                    "filename": file.filename,
                    "pdf_path": pdf_path,
                    "uploaded_at": datetime.now().isoformat(),
                    "text_preview": text[:500],
                    "full_text": text  # Store full text for user resumes since fewer in number
                }
            )
        ]
    )
    
    return {
        "resume_id": resume_id,
        "resume_name": resume_name,
        "filename": file.filename
    }

@app.get("/api/user/resumes")
async def list_user_resumes(request: Request):
    """List all user-uploaded resumes"""
    require_role(request, ["user"])
    # Scroll through user resumes
    scroll_result = qdrant_client.scroll(
        collection_name="resumes",
        scroll_filter=Filter(
            must=[
                FieldCondition(
                    key="user_uploaded",
                    match=MatchValue(value=True)
                )
            ]
        ),
        limit=MAX_SCALE,
        with_payload=True,
        with_vectors=False
    )
    
    resumes = []
    for point in scroll_result[0]:
        resumes.append({
            "resume_id": point.id,
            "resume_name": point.payload.get("resume_name"),
            "filename": point.payload.get("filename"),
            "uploaded_at": point.payload.get("uploaded_at")
        })
    
    return {"resumes": resumes}

@app.post("/api/user/resumes/{resume_id}/match-jobs")
async def match_resume_to_jobs(request: Request, resume_id: str, job_descriptions: List[dict]):
    require_role(request, ["user"])
    """
    Match a user's resume against multiple job descriptions.
    Expected format: [{"name": "Job Title", "description": "Job details..."}, ...]
    """
    # Get resume
    try:
        resume_points = qdrant_client.retrieve(
            collection_name="resumes",
            ids=[resume_id],
            with_vectors=True
        )
        if not resume_points:
            raise HTTPException(status_code=404, detail="Resume not found")
        
        resume_point = resume_points[0]
        resume_vector = resume_point.vector
        resume_text = resume_point.payload.get("full_text", resume_point.payload.get("text_preview", ""))
    except:
        raise HTTPException(status_code=404, detail="Resume not found")
    
    # Calculate similarity with each job description
    job_matches = []
    for job in job_descriptions:
        job_name = job.get("name", "Untitled Job")
        job_desc = job.get("description", "")
        
        if not job_desc:
            continue
        
        # Generate embedding for job description
        job_embedding = embedding_model.encode(job_desc)
        
        # Calculate cosine similarity
        similarity = cos_sim(resume_vector, job_embedding.tolist())
        score = float(similarity[0][0]) if len(similarity.shape) > 1 else float(similarity[0])
        
        # Generate explanation for high matches
        explanation = _generate_explanation(resume_text, job_desc, score)
        
        job_matches.append({
            "job_name": job_name,
            "description": job_desc,
            "score": score,
            "explanation": explanation
        })
    
    # Sort by score descending
    job_matches.sort(key=lambda x: x["score"], reverse=True)
    
    # Add ranks
    for rank, match in enumerate(job_matches, 1):
        match["rank"] = rank
        # Only keep explanation for top 3
        if rank > 3:
            match["explanation"] = None
    
    return {"job_matches": job_matches}

@app.get("/api/user/resumes/{resume_id}/latest-matches")
async def get_latest_matches(request: Request, resume_id: str):
    require_role(request, ["user"])
    """Get the most recent cached matching results for a resume"""
    try:
        # Get all analysis results for this resume, sorted by timestamp
        scroll_result = qdrant_client.scroll(
            collection_name="analysis_results",
            scroll_filter=Filter(
                must=[
                    FieldCondition(
                        key="resume_id",
                        match=MatchValue(value=resume_id)
                    ),
                    FieldCondition(
                        key="result_type",
                        match=MatchValue(value="user_matching")
                    )
                ]
            ),
            limit=10,
            with_vectors=False,
            with_payload=True
        )
        
        if not scroll_result[0]:
            return {"has_cached_results": False}
        
        # Sort by timestamp and get the most recent
        results = scroll_result[0]
        results.sort(key=lambda x: x.payload.get("timestamp", ""), reverse=True)
        latest = results[0]
        
        job_matches = json.loads(latest.payload.get("results_json", "[]"))
        
        return {
            "has_cached_results": True,
            "timestamp": latest.payload.get("timestamp"),
            "job_count": latest.payload.get("job_count", 0),
            "job_matches": job_matches
        }
    except Exception as e:
        return {"has_cached_results": False, "error": str(e)}

# ----------------------------------------------------------------------
# USER JOB DESCRIPTIONS LIBRARY
# ----------------------------------------------------------------------

@app.post("/api/user/job-descriptions")
async def add_user_job_description(request: Request, job_data: dict):
    require_role(request, ["user"])
    """
    Add a job description to the user's personal library for future matching.
    Expected format: {"name": "Job Title", "description": "Job details..."}
    """
    job_name = job_data.get("name", "").strip()
    job_description = job_data.get("description", "").strip()
    
    if not job_name or not job_description:
        raise HTTPException(status_code=400, detail="Job name and description are required")
    
    # Generate embedding
    embedding = embedding_model.encode(job_description)
    
    # Create unique ID
    job_id = str(uuid.uuid4())
    
    # Store in Qdrant
    qdrant_client.upsert(
        collection_name="user_job_descriptions",
        points=[
            PointStruct(
                id=job_id,
                vector=embedding.tolist(),
                payload={
                    "user_id": "default",  # Could be extended for multi-user
                    "job_name": job_name,
                    "description_text": job_description,
                    "created_at": datetime.now().isoformat()
                }
            )
        ]
    )
    
    return {
        "job_description_id": job_id,
        "job_name": job_name,
        "created_at": datetime.now().isoformat()
    }

@app.get("/api/user/job-descriptions")
async def list_user_job_descriptions(request: Request):
    require_role(request, ["user"])
    """Get all saved job descriptions from the user's library"""
    scroll_result = qdrant_client.scroll(
        collection_name="user_job_descriptions",
        scroll_filter=Filter(
            must=[
                FieldCondition(
                    key="user_id",
                    match=MatchValue(value="default")
                )
            ]
        ),
        limit=100,
        with_vectors=False
    )
    
    jobs = []
    for point in scroll_result[0]:
        jobs.append({
            "job_description_id": point.id,
            "job_name": point.payload.get("job_name"),
            "description_text": point.payload.get("description_text"),
            "created_at": point.payload.get("created_at")
        })
    
    # Sort by most recent first
    jobs.sort(key=lambda x: x.get("created_at", ""), reverse=True)
    
    return {"job_descriptions": jobs}

@app.delete("/api/user/job-descriptions/{job_id}")
async def delete_user_job_description(request: Request, job_id: str):
    require_role(request, ["user"])
    """Delete a saved job description from the user's library"""
    try:
        qdrant_client.delete(
            collection_name="user_job_descriptions",
            points_selector=[job_id]
        )
        return {"message": "Job description deleted successfully"}
    except Exception as exc:
        raise HTTPException(status_code=404, detail=f"Job description not found: {exc}")

@app.post("/api/user/resumes/{resume_id}/match-saved-jobs")
async def match_resume_to_saved_jobs(request: Request, resume_id: str):
    require_role(request, ["user"])
    """
    Match a user's resume against their saved job descriptions library.
    """
    # Get resume
    try:
        resume_points = qdrant_client.retrieve(
            collection_name="resumes",
            ids=[resume_id],
            with_vectors=True
        )
        if not resume_points:
            raise HTTPException(status_code=404, detail="Resume not found")
        
        resume_point = resume_points[0]
        resume_vector = resume_point.vector
        resume_text = resume_point.payload.get("full_text", resume_point.payload.get("text_preview", ""))
    except:
        raise HTTPException(status_code=404, detail="Resume not found")
    
    # Get all saved job descriptions
    scroll_result = qdrant_client.scroll(
        collection_name="user_job_descriptions",
        scroll_filter=Filter(
            must=[
                FieldCondition(
                    key="user_id",
                    match=MatchValue(value="default")
                )
            ]
        ),
        limit=100,
        with_vectors=True
    )
    
    if not scroll_result[0]:
        return {"job_matches": []}
    
    # Calculate similarity with each job
    job_matches = []
    for job_point in scroll_result[0]:
        job_vector = job_point.vector
        job_name = job_point.payload.get("job_name", "Untitled Job")
        job_desc = job_point.payload.get("description_text", "")
        
        # Calculate cosine similarity
        similarity = cos_sim(resume_vector, job_vector)
        score = float(similarity[0][0]) if len(similarity.shape) > 1 else float(similarity[0])
        
        # Generate explanation for high matches
        explanation = _generate_explanation(resume_text, job_desc, score)
        
        job_matches.append({
            "job_description_id": job_point.id,
            "job_name": job_name,
            "description": job_desc,
            "score": score,
            "explanation": explanation
        })
    
    # Sort by score descending
    job_matches.sort(key=lambda x: x["score"], reverse=True)
    
    # Add ranks
    for rank, match in enumerate(job_matches, 1):
        match["rank"] = rank
        # Only keep explanation for top 3
        if rank > 3:
            match["explanation"] = None
    
    # Store analysis results
    try:
        analysis_id = str(uuid.uuid4())
        qdrant_client.upsert(
            collection_name="analysis_results",
            points=[
                PointStruct(
                    id=analysis_id,
                    vector=[0] * 384,  # Placeholder vector
                    payload={
                        "resume_id": resume_id,
                        "result_type": "user_matching",
                        "results_json": json.dumps(job_matches),
                        "timestamp": datetime.now().isoformat(),
                        "job_count": len(job_matches)
                    }
                )
            ]
        )
    except:
        pass  # Silently fail if analysis_results collection doesn't exist yet
    
    return {"job_matches": job_matches}

# ----------------------------------------------------------------------
# UTILITY ENDPOINTS
# ----------------------------------------------------------------------

@app.get("/api/resumes/{resume_id}/pdf")
async def get_resume_pdf(resume_id: str):
    """Serve a resume PDF file"""
    try:
        resume_points = qdrant_client.retrieve(
            collection_name="resumes",
            ids=[resume_id]
        )
        if not resume_points:
            raise HTTPException(status_code=404, detail="Resume not found")
        
        pdf_path = resume_points[0].payload.get("pdf_path")
        if not pdf_path or not os.path.exists(pdf_path):
            raise HTTPException(status_code=404, detail="PDF file not found")
        
        return FileResponse(
            pdf_path,
            media_type="application/pdf",
            headers={"Content-Disposition": "inline"}
        )
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Error retrieving PDF: {exc}")

@app.delete("/api/hr/jobs/{job_id}")
async def delete_job(request: Request, job_id: str):
    """Delete a job and all associated resumes"""
    require_role(request, ["hr"])
    # Get all resumes for this job
    scroll_result = qdrant_client.scroll(
        collection_name="resumes",
        scroll_filter=Filter(
            must=[
                FieldCondition(
                    key="job_id",
                    match=MatchValue(value=job_id)
                )
            ]
        ),
        limit=MAX_SCALE,
        with_payload=True,
        with_vectors=False
    )
    
    # Delete PDF files
    deleted_count = 0
    for point in scroll_result[0]:
        pdf_path = point.payload.get("pdf_path")
        if pdf_path and os.path.exists(pdf_path):
            try:
                os.remove(pdf_path)
                deleted_count += 1
            except Exception as exc:
                print(f"[WARN] Could not delete file {pdf_path}: {exc}")
        
        # Delete from Qdrant
        qdrant_client.delete(
            collection_name="resumes",
            points_selector=[point.id]
        )
    
    # Delete job description
    try:
        qdrant_client.delete(
            collection_name="job_descriptions",
            points_selector=[job_id]
        )
    except:
        pass
    
    return {"deleted_resumes": deleted_count, "message": "Job and associated resumes deleted"}

@app.delete("/api/user/resumes/{resume_id}")
async def delete_user_resume(request: Request, resume_id: str):
    require_role(request, ["user"])
    """Delete a user-uploaded resume"""
    try:
        # Get resume details
        resume_points = qdrant_client.retrieve(
            collection_name="resumes",
            ids=[resume_id]
        )
        if not resume_points:
            raise HTTPException(status_code=404, detail="Resume not found")
        
        # Delete PDF file
        pdf_path = resume_points[0].payload.get("pdf_path")
        if pdf_path and os.path.exists(pdf_path):
            os.remove(pdf_path)
        
        # Delete from Qdrant
        qdrant_client.delete(
            collection_name="resumes",
            points_selector=[resume_id]
        )
        
        return {"success": True, "message": "Resume deleted"}
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Error deleting resume: {exc}")

@app.get("/")
async def root():
    """API health check"""
    return {
        "status": "online",
        "service": "Resume Analyzer API",
        "version": "2.0.0",
        "features": {
            "embedding_model": "all-MiniLM-L6-v2",
            "vector_db": "Qdrant (local)",
            "ai_explanations": groq_client is not None
        }
    }

# ----------------------------------------------------------------------
# Run server directly if this file is executed
# ----------------------------------------------------------------------
if __name__ == "__main__":
    import uvicorn
    
    print("🚀 Starting server with uvicorn...")
    print("📍 Server will be available at: http://localhost:8080")
    print("📖 API docs at: http://localhost:8080/docs")
    print("⚡ Press Ctrl+C to stop")
    print("")
    
    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=8080,
        reload=True,
        log_level="info"
    )