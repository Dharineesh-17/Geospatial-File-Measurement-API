from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
UPLOAD_DIR = BASE_DIR / "uploads"
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)

# Allowed file extensions
ALLOWED_EXTENSIONS = {".zip", ".kml"}
MAX_FILE_SIZE_BYTES = 50 * 1024 * 1024  # 50 MB
DEFAULT_CRS = "EPSG:4326"
