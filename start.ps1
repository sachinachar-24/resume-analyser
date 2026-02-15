# Resume Analyzer - Quick Start Script
# This script helps you get started quickly

Write-Host "========================================" -ForegroundColor Cyan
Write-Host "  Resume Analyzer - Quick Start Setup" -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan
Write-Host ""

# Check Python installation
Write-Host "1. Checking Python installation..." -ForegroundColor Yellow
$pythonVersion = & python --version 2>&1
if ($LASTEXITCODE -eq 0) {
    Write-Host "   ✓ Python found: $pythonVersion" -ForegroundColor Green
} else {
    Write-Host "   ✗ Python not found! Please install Python 3.8+" -ForegroundColor Red
    Write-Host "   Download from: https://www.python.org/downloads/" -ForegroundColor Yellow
    exit 1
}

# Navigate to backend directory
Set-Location -Path "backend"

# Check if virtual environment exists
Write-Host ""
Write-Host "2. Setting up virtual environment..." -ForegroundColor Yellow
if (Test-Path "venv") {
    Write-Host "   ✓ Virtual environment already exists" -ForegroundColor Green
} else {
    Write-Host "   Creating virtual environment..." -ForegroundColor Cyan
    python -m venv venv
    Write-Host "   ✓ Virtual environment created" -ForegroundColor Green
}

# Activate virtual environment
Write-Host ""
Write-Host "3. Activating virtual environment..." -ForegroundColor Yellow
& ".\venv\Scripts\Activate.ps1"
Write-Host "   ✓ Virtual environment activated" -ForegroundColor Green

# Install dependencies
Write-Host ""
Write-Host "4. Installing dependencies..." -ForegroundColor Yellow
Write-Host "   This may take 3-5 minutes on first run (downloading PyTorch ~1.5GB)" -ForegroundColor Cyan

# Check if uv is available
$uvAvailable = Get-Command uv -ErrorAction SilentlyContinue
if ($uvAvailable) {
    Write-Host "   Using uv for faster installation..." -ForegroundColor Cyan
    uv sync --quiet
} else {
    Write-Host "   Using pip for installation..." -ForegroundColor Cyan
    pip install -r requirements.txt --quiet
}

if ($LASTEXITCODE -eq 0) {
    Write-Host "   ✓ Dependencies installed successfully" -ForegroundColor Green
} else {
    Write-Host "   ✗ Failed to install dependencies" -ForegroundColor Red
    exit 1
}

# Check if .env exists
Write-Host ""
Write-Host "5. Checking environment configuration..." -ForegroundColor Yellow
if (Test-Path ".env") {
    Write-Host "   ✓ .env file found" -ForegroundColor Green
} else {
    Write-Host "   Creating .env from template..." -ForegroundColor Cyan
    Copy-Item ".env.example" ".env"
    Write-Host "   ✓ .env file created (edit this file to add your GROQ_API_KEY)" -ForegroundColor Green
    Write-Host "   Note: App works without GROQ_API_KEY, but won't show AI explanations" -ForegroundColor Yellow
}

# Start the server
Write-Host ""
Write-Host "========================================" -ForegroundColor Cyan
Write-Host "  Setup Complete!" -ForegroundColor Green
Write-Host "========================================" -ForegroundColor Cyan
Write-Host ""
Write-Host "Starting backend server..." -ForegroundColor Yellow
Write-Host ""
Write-Host "Once server is running:" -ForegroundColor Cyan
Write-Host "1. Open your browser" -ForegroundColor White
Write-Host "2. Navigate to: file:///$(Get-Location)/../frontend/index.html" -ForegroundColor White
Write-Host "   OR double-click: frontend/index.html" -ForegroundColor White
Write-Host ""
Write-Host "Press Ctrl+C to stop the server" -ForegroundColor Yellow
Write-Host ""

# Start server (simple method)
python main.py
