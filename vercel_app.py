import os
import sys

# Tell the app where the root is (Vercel needs this for your paths)
ROOT = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, ROOT)
os.environ["APP_ROOT"] = ROOT

# Import the actual FastAPI instance from your routes file
from routes import app

# Vercel will now find this 'app' variable automatically
