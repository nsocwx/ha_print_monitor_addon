"""Application version metadata."""
import os

APP_VERSION = os.getenv("APP_VERSION", "0.3.11")
BUILD_DATE = os.getenv("BUILD_DATE", "unknown")
GIT_COMMIT = os.getenv("GIT_COMMIT", "unknown")
