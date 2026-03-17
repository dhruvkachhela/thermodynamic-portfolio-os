"""
RUN THE APP
===========
Run this from inside the portfolio_app folder:

    cd portfolio_app
    python run.py

Then open: http://localhost:8000
"""

import sys, os, subprocess

# ── This is the ROOT of the project (the folder containing run.py) ────────────
ROOT = os.path.dirname(os.path.abspath(__file__))

def check_packages():
    required = ["fastapi", "uvicorn", "yfinance", "numpy", "scipy", "sqlalchemy"]
    missing  = []
    for pkg in required:
        try:
            __import__(pkg)
        except ImportError:
            missing.append(pkg)

    if missing:
        print(f"📦 Installing: {', '.join(missing)}")
        subprocess.check_call([sys.executable, "-m", "pip", "install", *missing, "-q"])
        print("✅ Packages installed")

if __name__ == "__main__":
    print("=" * 55)
    print("  THERMODYNAMIC PORTFOLIO OS")
    print("=" * 55)

    check_packages()

    # Add ROOT to sys.path so all imports work
    if ROOT not in sys.path:
        sys.path.insert(0, ROOT)

    # Set an environment variable so routes.py can find ROOT reliably
    os.environ["APP_ROOT"] = ROOT

    print(f"📁 Project root: {ROOT}")
    print(f"📁 Frontend:     {os.path.join(ROOT, 'frontend')}")
    print(f"📁 Database:     {os.path.join(ROOT, 'portfolio.db')}")
    print()

    import uvicorn
    from routes import app

    print("✅ App loaded successfully")
    print()
    print("🌐  Dashboard → http://localhost:8000")
    print("📖  API Docs  → http://localhost:8000/docs")
    print("🛑  Stop      → press CTRL+C")
    print()

    uvicorn.run(app, host="0.0.0.0", port=8000, reload=False, log_level="info")