from fastapi import APIRouter

router = APIRouter(tags=["Health"])


@router.get("/api/health/")
async def health_check():
    """Health check endpoint to verify API service status."""
    return {
        "status": "healthy",
        "service": "Geospatial File Measurement API",
        "supported_formats": [".zip (Shapefile)", ".kml"],
        "measurement_support": {
            "Polygon / MultiPolygon": "Area (m², km², ha)",
            "LineString / MultiLineString": "Length (m, km)",
            "Point / MultiPoint": "Gracefully reported (no area/length)"
        }
    }
