"""Entry point for the application."""
import sys
import os

# Add app directory to path
sys.path.insert(0, os.path.dirname(__file__))

from main import app

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8080)
