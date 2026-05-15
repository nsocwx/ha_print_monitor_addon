"""Utility functions for the application."""
import hashlib
import uuid
from datetime import datetime
from pathlib import Path


def generate_event_id() -> str:
    """Generate a unique event ID."""
    return f"event_{uuid.uuid4().hex[:8]}"


def generate_capture_id() -> str:
    """Generate a unique capture ID."""
    return f"capture_{uuid.uuid4().hex[:8]}"


def file_hash(data: bytes) -> str:
    """Compute MD5 hash of data."""
    return hashlib.md5(data).hexdigest()


def safe_path(base_dir: Path, filename: str) -> Path:
    """Get safe path with directory traversal protection."""
    # Remove any path separators from filename
    safe_name = filename.replace("../", "").replace("..\\", "").split("/")[-1]
    result = (base_dir / safe_name).resolve()
    
    # Ensure result is within base_dir
    if not str(result).startswith(str(base_dir.resolve())):
        raise ValueError(f"Path traversal attempt: {filename}")
    
    return result


def format_certainty(value: float) -> str:
    """Format certainty as percentage string."""
    return f"{int(value * 100)}%"


def format_duration(seconds: float) -> str:
    """Format duration in human-readable form."""
    if seconds < 60:
        return f"{int(seconds)}s"
    elif seconds < 3600:
        return f"{int(seconds // 60)}m"
    else:
        hours = seconds // 3600
        minutes = (seconds % 3600) // 60
        return f"{int(hours)}h {int(minutes)}m"
