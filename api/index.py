"""Vercel serverless entry point — re-exports the FastAPI app."""

import sys
import os

# Add project root to path so imports work on Vercel
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from main import app
