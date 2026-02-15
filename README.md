# Resume Analyzer - AI-Powered Resume Matching

A full-stack resume analysis application that uses AI-powered similarity search to match resumes with job descriptions. Built with plain Python (FastAPI) backend and vanilla HTML/CSS/JavaScript frontend.

## Features

### For HR Professionals
- Create and manage job postings
- Upload multiple resumes for each job posting
- AI-powered ranking of resumes based on job description similarity
- View detailed match scores and AI-generated explanations for top candidates
- View and download resume PDFs directly in the browser

### For Job Seekers
- Upload and manage multiple versions of your resume
- Add multiple job descriptions to compare
- Get AI-powered matching scores for each job
- Receive detailed explanations on which jobs best match your skills
- Discover which positions align best with your experience

## Technology Stack

### Backend
- **FastAPI** - Modern Python web framework
- **Sentence Transformers** - `all-MiniLM-L6-v2` model for semantic embeddings (384 dimensions)
- **Qdrant** - Vector database with local SQLite storage
- **pypdf** - PDF text extraction
- **Groq API** - Optional AI explanations for top matches (uses Llama 3.3 70B)

### Frontend
- Pure HTML5, CSS3, and JavaScript
- No frameworks - lightweight and fast
- Responsive design for desktop and mobile
- Real-time updates and smooth animations

## Installation

### Prerequisites
- Python 3.8 or higher
- pip (Python package installer) OR uv (recommended for faster installs)
- ~2.5 GB free disk space (for PyTorch and embedding model)

**Optional: Install uv for faster package management**
```bash
# Windows (PowerShell)
powershell -c "irm https://astral.sh/uv/install.ps1 | iex"

# macOS/Linux
curl -LsSf https://astral.sh/uv/install.sh | sh
```

### Step 1: Clone or Navigate to Project
```bash
cd c:\Users\poovx\Desktop\session-project\resume-analyser
```

### Step 2: Set Up Python Environment (Recommended)
```bash
# Create virtual environment
python -m venv venv

# Activate virtual environment
# On Windows:
venv\Scripts\activate
# On macOS/Linux:
# source venv/bin/activate
```

### Step 3: Install Dependencies

**Option A: Using uv (Recommended - Faster)**
```bash
cd backend
uv sync
```

**Option B: Using pip (Traditional)**
```bash
cd backend
pip install -r requirements.txt
```

**Note:** First installation may take 3-5 minutes as it downloads PyTorch (~1.5GB) and the embedding model (~80MB).

### Step 4: Configure Environment Variables
```bash
# Copy example environment file
copy .env.example .env

# Edit .env file with your settings
notepad .env
```

**Environment Variables:**
- `GROQ_API_KEY` - (Optional) For AI explanations. Get free key from https://console.groq.com
- `EXPLANATION_THRESHOLD` - Minimum score (0-1) to trigger AI explanations (default: 0.6)
- `MAX_SCALE` - Maximum resumes/jobs to handle (default: 200)
- `QDRANT_PATH` - Path to store vector database (default: ./qdrant_storage)

**Note:** The application works without `GROQ_API_KEY`, but you won't get AI-generated explanations for matches.

## Running the Application

### Start Backend Server

**Option 1: Simple (Recommended)**
```bash
cd backend
python main.py
```

**Option 2: With uv (faster)**
```bash
cd backend
uv run main.py
```

**Option 3: Traditional uvicorn command**
```bash
cd backend
python -m uvicorn main:app --reload --host 0.0.0.0 --port 8000
```

All three methods work identically - choose whichever you prefer!

You should see:
```
🚀 Starting Resume Analyzer...
✓ Upload directories created
📦 Loading embedding model (all-MiniLM-L6-v2)...
✓ Embedding model loaded
💾 Initializing Qdrant database...
✓ Created 'resumes' collection
✓ Created 'job_descriptions' collection
✅ Resume Analyzer ready!

INFO:     Uvicorn running on http://0.0.0.0:8000
```

### Open Frontend
Open your web browser and navigate to:
```
file:///c:/Users/poovx/Desktop/session-project/resume-analyser/frontend/index.html
```

Or simply double-click `frontend/index.html` to open in your default browser.

## Usage Guide

### HR Portal Workflow

1. **Create Job Posting**
   - Click "For HR Professionals" on homepage
   - Click "+ Create Job Posting"
   - Enter job title and detailed description
   - Click "Create Job"

2. **Upload Resumes**
   - Click "📄 Upload Resumes" on any job card
   - Select multiple PDF files
   - Wait for processing (shows progress)

3. **Rank Resumes**
   - Click "🎯 Rank Resumes" on job card
   - View ranked list with match scores
   - Top 3 matches include AI explanations (if Groq API configured)
   - Click "📄 View PDF" to open any resume

4. **Manage Jobs**
   - Delete jobs and associated resumes with "Delete" button
   - Resume count updates automatically

### Job Seeker Portal Workflow

1. **Upload Resume**
   - Click "For Job Seekers" on homepage
   - Click "+ Upload" in sidebar
   - Enter resume name and select PDF
   - Upload (can upload multiple versions)

2. **Add Job Descriptions**
   - Select a resume from sidebar
   - Click "+ Add Job Description"
   - Paste job title and full description
   - Add multiple jobs to compare

3. **Analyze Matches**
   - Click "🎯 Analyze Job Matches"
   - View ranked jobs by compatibility
   - Read AI explanations for top 3 matches
   - Expand job descriptions to review details

4. **Manage Resumes**
   - View PDF icon to open resume
   - Delete icon (🗑️) to remove resume
   - Switch between different resume versions

## API Endpoints

### HR Endpoints
- `POST /api/hr/jobs` - Create job posting
- `GET /api/hr/jobs` - List all jobs
- `POST /api/hr/jobs/{job_id}/resumes` - Upload resumes for job
- `POST /api/hr/jobs/{job_id}/rank` - Rank resumes for job
- `DELETE /api/hr/jobs/{job_id}` - Delete job and resumes

### User Endpoints
- `POST /api/user/resumes` - Upload user resume
- `GET /api/user/resumes` - List user resumes
- `POST /api/user/resumes/{resume_id}/match-jobs` - Match resume to jobs
- `DELETE /api/user/resumes/{resume_id}` - Delete resume

### Utility Endpoints
- `GET /api/resumes/{resume_id}/pdf` - Serve resume PDF
- `GET /` - API health check

## Project Structure

```
resume-analyser/
├── backend/
│   ├── main.py              # FastAPI application with all endpoints
│   ├── requirements.txt     # Python dependencies
│   ├── .env.example         # Environment variables template
│   ├── .env                 # Your configuration (create this)
│   ├── uploads/             # PDF storage (auto-created)
│   │   ├── resumes/         # Uploaded resume PDFs
│   │   └── jobs/            # Job-related files
│   └── qdrant_storage/      # Vector database (auto-created)
└── frontend/
    ├── index.html           # Homepage with portal selection
    ├── hr.html              # HR interface
    ├── user.html            # Job seeker interface
    ├── styles.css           # Shared styles
    └── script.js            # Shared JavaScript utilities
```

## How It Works

### Similarity Search Process

1. **Text Extraction**: PDF resumes are parsed using pypdf to extract plain text

2. **Embedding Generation**: Text is converted to 384-dimensional vectors using the `all-MiniLM-L6-v2` model from sentence-transformers

3. **Vector Storage**: Embeddings are stored in Qdrant vector database with metadata (filename, upload date, etc.)

4. **Similarity Search**: When matching:
   - Job description is converted to embedding
   - Qdrant performs cosine similarity search against stored resumes
   - Results ranked by score (0-1, where 1 is perfect match)

5. **AI Explanations** (Optional): For top 3 matches above threshold:
   - Resume text + job description sent to Groq API
   - Llama 3.3 70B generates human-readable explanation
   - Explanation displayed alongside score

### Why This Stack?

- **Sentence Transformers**: State-of-the-art semantic similarity, runs locally, no API costs
- **Qdrant Local Mode**: Persistent storage without Docker, perfect for single-machine deployment
- **FastAPI**: Modern Python, auto-generated docs, async support
- **Plain Frontend**: No build process, works offline, easy to customize

## Troubleshooting

### Backend won't start
- Ensure Python 3.8+ installed: `python --version`
- Activate virtual environment
- Reinstall dependencies: `pip install -r requirements.txt`

### "Model download failed"
- Check internet connection
- Model downloads from HuggingFace on first run (~80MB)
- Manual download: Models cache to `~/.cache/torch/sentence_transformers/`

### "No such collection" errors
- Delete `qdrant_storage` folder and restart server
- Collections auto-recreate on startup

### PDFs not extracting text
- pypdf works best with text-based PDFs
- Scanned/image PDFs may fail (no OCR included)
- Try re-saving PDF with "Save as Text PDF" option

### Slow ranking/matching
- First run loads model (~2 seconds)
- Subsequent matches: ~100ms per resume
- Large PDFs (50+ pages) take longer to process
- Consider upgrading to `all-mpnet-base-v2` for better quality (slower)

### "CORS error" in browser console
- Backend must be running on `http://localhost:8000`
- Check backend terminal for errors
- Ensure CORS middleware enabled (already configured)

### No AI explanations showing
- Check `GROQ_API_KEY` in `.env` file
- Verify API key is valid at https://console.groq.com
- Check match score exceeds `EXPLANATION_THRESHOLD`
- Free tier: 14,400 requests/day (plenty for testing)

## Performance Notes

- **Initial Startup**: 10-30 seconds (model loading)
- **Resume Upload**: 1-2 seconds per PDF
- **Ranking**: <1 second for 10 resumes, ~2 seconds for 50 resumes
- **Memory Usage**: ~300-500MB with 100 resumes indexed
- **Storage**: ~1.5KB per resume embedding

## Upgrading & Customization

### Use Better Embedding Model
Edit [backend/main.py](backend/main.py) line 72:
```python
embedding_model = SentenceTransformer('all-mpnet-base-v2')  # Higher quality
```
Note: Must update `VectorParams(size=768)` in collection creation.

### Change Similarity Threshold
Edit `.env`:
```
EXPLANATION_THRESHOLD=0.7  # More strict (0.6 is default)
```

### Add Authentication
FastAPI supports OAuth2, JWT tokens. Add dependency to protect endpoints.

### Deploy to Production
- Use Gunicorn/Uvicorn with multiple workers
- Switch to Qdrant server mode for scaling
- Add Redis for caching
- Use proper file storage (S3, MinIO)

## Contributing

This is a complete standalone project. Feel free to:
- Add more embedding models
- Integrate other LLMs for explanations
- Add user authentication
- Build mobile app using the API
- Add resume parsing for structured data extraction

## License

This project is provided as-is for educational and commercial use.

## Support

For issues or questions:
1. Check troubleshooting section above
2. Verify all dependencies installed correctly
3. Check backend logs for errors
4. Ensure `.env` configured properly

## Version History

**v2.0.0** - Complete rewrite
- Dual interface (HR + Job Seeker)
- Vector similarity search with Qdrant
- Optional Groq AI explanations
- Persistent storage
- Modern responsive UI

---

**Built with ❤️ using Python, FastAPI, and Sentence Transformers**
