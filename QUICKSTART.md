# Quick Start - Manual Steps

If the automated script doesn't work, follow these manual steps:

## Step 1: Open PowerShell/Terminal
Navigate to the backend directory:
```powershell
cd backend
```

## Step 2: Create Virtual Environment (First time only)
```powershell
python -m venv venv
```

## Step 3: Activate Virtual Environment
```powershell
# On Windows PowerShell:
.\venv\Scripts\Activate.ps1

# On Windows CMD:
.\venv\Scripts\activate.bat

# On macOS/Linux:
source venv/bin/activate
```

## Step 4: Install Dependencies (First time only)

**With uv (faster):**
```powershell
uv sync
```

**Or with pip (traditional):**
```powershell
uv pip install -r requirements.txt
```
**Note:** This takes 3-5 minutes on first run (~2GB download)

## Step 5: Create .env File (First time only)
```powershell
copy .env.example .env
```
Then edit `.env` to add your GROQ_API_KEY (optional)

## Step 6: Start Server

**Simplest way:**
```powershell
python main.py
```

**Or with uv (faster):**
```powershell
uv run main.py
```

**Or traditional way:**
```powershell
python -m uvicorn main:app --reload --host 0.0.0.0 --port 8000
```

## Step 7: Open Frontend
Open browser and go to:
```
file:///C:/Users/poovx/Desktop/session-project/resume-analyser/frontend/index.html
```

Or double-click: `frontend/index.html`

## Verify It Works
You should see:
- Backend: Startup messages in terminal with "✅ Resume Analyzer ready!"
- Frontend: Homepage with two cards (HR and User portals)

## Troubleshooting
- **"python not found"**: Install Python 3.8+ from python.org
- **"cannot activate venv"**: Run `Set-ExecutionPolicy -ExecutionPolicy RemoteSigned -Scope CurrentUser`
- **"port already in use"**: Change port with `--port 8001`
- **Frontend can't connect**: Ensure backend running on http://localhost:8000

## Need Help?
Check the full README.md for detailed troubleshooting and usage guide.
