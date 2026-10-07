from pathlib import Path
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles

from app.routes import files_router, health_router
from app.config import BASE_DIR

app = FastAPI(
    title="Geospatial File Measurement API",
    description="""
A robust, production-grade REST API service built with FastAPI to process geospatial files 
(.zip containing Shapefile or .kml), extract spatial features, dynamically handle Coordinate 
Reference Systems (CRS) and geographic projections, and compute precise geometric measurements 
(Polygon Area, LineString Length, and Point handling).
    """,
    version="1.0.0",
    docs_url="/docs",
    redoc_url="/redoc"
)

# CORS configuration
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include Routers
app.include_router(health_router)
app.include_router(files_router)

# Mount static and sample files
static_dir = BASE_DIR / "app" / "static"
samples_dir = BASE_DIR / "samples"
samples_dir.mkdir(parents=True, exist_ok=True)

if samples_dir.exists():
    app.mount("/samples", StaticFiles(directory=str(samples_dir)), name="samples")


@app.get("/", response_class=HTMLResponse, tags=["Dashboard"])
async def dashboard():
    """Serves the interactive geospatial measurement dashboard."""
    index_file = static_dir / "index.html"
    if index_file.exists():
        return FileResponse(index_file)
    return HTMLResponse("<h1>Geospatial File Measurement API is running. Visit /docs for Swagger UI.</h1>")
