# Using UV with Resume Analyzer

UV is a modern, fast Python package manager. Here's how to use it with this project:

## Installation

```powershell
# Windows (PowerShell - Run as Administrator recommended)
powershell -c "irm https://astral.sh/uv/install.ps1 | iex"

# Or download from: https://github.com/astral-sh/uv
```

## Quick Commands

### First Time Setup
```powershell
cd backend

# Install all dependencies (creates .venv automatically)
uv sync

# Or if you just want to add the project dependencies
uv venv
uv pip install -e .
```

### Running the Server
```powershell
# Option 1: Direct run (uv manages the environment)
uv run main.py

# Option 2: Activate venv then run normally
.venv\Scripts\Activate.ps1
python main.py
```

### Adding New Dependencies
```powershell
# Add a new package
uv add package-name

# Add a dev dependency
uv add --dev pytest

# Update pyproject.toml and install
uv sync
```

### Other Useful Commands
```powershell
# Update all dependencies
uv sync --upgrade

# Remove a package
uv remove package-name

# Show installed packages
uv pip list

# Export to requirements.txt (for compatibility)
uv pip freeze > requirements.txt
```

## Why Use UV?

✅ **10-100x faster** than pip
✅ **Automatic virtual environment** management
✅ **Better dependency resolution**
✅ **Compatible with pip** - can fall back anytime
✅ **Works with pyproject.toml** - modern Python standard

## Troubleshooting

### "uv: command not found"
- Restart your terminal after installation
- Or add to PATH: `$env:PATH += ";$HOME\.cargo\bin"`

### "No `pyproject.toml` found"
- Make sure you're in the `backend/` directory
- The `pyproject.toml` file should be there

### Dependencies not installing
```powershell
# Clear cache and retry
uv cache clean
uv sync --reinstall
```

### Want to use pip instead?
No problem! Just use the regular commands:
```powershell
pip install -r requirements.txt
python main.py
```

Both work perfectly - uv is just faster! 🚀
