import os
import uuid
import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import List, Optional

from fastapi import APIRouter, UploadFile, File, HTTPException, status
from fastapi.responses import JSONResponse

from app.config import UPLOAD_DIR, ALLOWED_EXTENSIONS, MAX_FILE_SIZE_BYTES
from app.models.schemas import (
    FileUploadResponse,
    FileInfoResponse,
    FileMeasurementsResponse,
    MeasurementSummary,
    FeatureMeasurement,
    MeasurementValues,
    GeometrySummary,
)
from app.services.storage import storage
from app.services.parser import process_geospatial_file

router = APIRouter(prefix="/api/files", tags=["Geospatial Files"])


@router.post("/", response_model=FileUploadResponse, status_code=status.HTTP_201_CREATED)
async def upload_geospatial_file(file: UploadFile = File(...)):
    """Upload and process a geospatial file (.zip containing Shapefile or .kml)."""
    filename = file.filename or "unknown"
    ext = Path(filename).suffix.lower()

    if ext not in ALLOWED_EXTENSIONS:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Unsupported file format '{ext}'. Allowed formats: {', '.join(ALLOWED_EXTENSIONS)} (.zip containing Shapefile or .kml)."
        )

    file_id = uuid.uuid4().hex[:8]
    dest_dir = UPLOAD_DIR / file_id
    dest_dir.mkdir(parents=True, exist_ok=True)
    dest_path = dest_dir / filename

    try:
        # Stream save file
        file_size = 0
        with open(dest_path, "wb") as buffer:
            while chunk := await file.read(1024 * 1024):
                file_size += len(chunk)
                if file_size > MAX_FILE_SIZE_BYTES:
                    raise HTTPException(
                        status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                        detail=f"File exceeds maximum allowed size of {MAX_FILE_SIZE_BYTES // (1024 * 1024)} MB."
                    )
                buffer.write(chunk)

        # Process the file
        processed_data = process_geospatial_file(dest_path, filename)

        # Save record
        record = {
            "id": file_id,
            "filename": filename,
            "file_type": processed_data["file_type"],
            "file_path": str(dest_path),
            "feature_count": processed_data["feature_count"],
            "crs": processed_data["crs"],
            "projected_crs": processed_data["projected_crs"],
            "status": "COMPLETED",
            "created_at": datetime.now(timezone.utc).isoformat(),
            "geometry_summary": processed_data["geometry_summary"],
            "summary": processed_data["summary"],
            "features": processed_data["features"]
        }
        storage.save(file_id, record)

        return FileUploadResponse(
            id=file_id,
            filename=filename,
            feature_count=processed_data["feature_count"],
            crs=processed_data["crs"],
            status="COMPLETED",
            message="Geospatial file uploaded and processed successfully."
        )

    except HTTPException:
        # Cleanup on known error
        if dest_dir.exists():
            shutil.rmtree(dest_dir, ignore_errors=True)
        raise
    except ValueError as ve:
        if dest_dir.exists():
            shutil.rmtree(dest_dir, ignore_errors=True)
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(ve))
    except Exception as e:
        if dest_dir.exists():
            shutil.rmtree(dest_dir, ignore_errors=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error processing geospatial file: {str(e)}"
        )


@router.get("/", response_model=List[FileInfoResponse])
async def list_files():
    """List all uploaded geospatial files."""
    records = storage.list_all()
    results = []
    for r in records:
        results.append(FileInfoResponse(
            id=r["id"],
            filename=r["filename"],
            feature_count=r["feature_count"],
            crs=r["crs"],
            status=r["status"],
            created_at=r.get("created_at"),
            file_type=r.get("file_type"),
            geometry_summary=GeometrySummary(**r["geometry_summary"]) if "geometry_summary" in r else None
        ))
    return results


@router.get("/{id}/", response_model=FileInfoResponse)
async def get_file_info(id: str):
    """Returns metadata and processing status for an uploaded file."""
    record = storage.get(id)
    if not record:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"File with id '{id}' not found."
        )

    return FileInfoResponse(
        id=record["id"],
        filename=record["filename"],
        feature_count=record["feature_count"],
        crs=record["crs"],
        status=record["status"],
        created_at=record.get("created_at"),
        file_type=record.get("file_type"),
        geometry_summary=GeometrySummary(**record["geometry_summary"]) if "geometry_summary" in record else None
    )


@router.get("/{id}/measurements/", response_model=FileMeasurementsResponse)
async def get_file_measurements(id: str):
    """Returns calculated measurements for all features in the file."""
    record = storage.get(id)
    if not record:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"File with id '{id}' not found."
        )

    features = []
    for f in record["features"]:
        m = f["measurements"]
        features.append(FeatureMeasurement(
            feature_id=f["feature_id"],
            geometry_type=f["geometry_type"],
            original_crs=f["original_crs"],
            projected_crs=f.get("projected_crs"),
            measurements=MeasurementValues(
                area_sq_meters=m.get("area_sq_meters"),
                area_sq_km=m.get("area_sq_km"),
                area_hectares=m.get("area_hectares"),
                length_meters=m.get("length_meters"),
                length_km=m.get("length_km"),
                note=m.get("note")
            ),
            properties=f.get("properties", {}),
            geometry=f.get("geometry")
        ))

    return FileMeasurementsResponse(
        id=record["id"],
        filename=record["filename"],
        crs=record["crs"],
        projected_crs=record.get("projected_crs"),
        feature_count=record["feature_count"],
        summary=MeasurementSummary(**record["summary"]),
        features=features
    )


@router.get("/{id}/geojson")
async def get_file_geojson(id: str):
    """Returns the features as a GeoJSON FeatureCollection."""
    record = storage.get(id)
    if not record:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"File with id '{id}' not found."
        )

    features_geojson = []
    for f in record["features"]:
        if f.get("geometry"):
            props = dict(f.get("properties", {}))
            props["_feature_id"] = f["feature_id"]
            props["_geometry_type"] = f["geometry_type"]
            props["_measurements"] = f["measurements"]
            features_geojson.append({
                "type": "Feature",
                "id": f["feature_id"],
                "geometry": f["geometry"],
                "properties": props
            })

    return {
        "type": "FeatureCollection",
        "file_id": record["id"],
        "filename": record["filename"],
        "crs": record["crs"],
        "features": features_geojson
    }


@router.delete("/{id}/", status_code=status.HTTP_200_OK)
async def delete_file(id: str):
    """Deletes an uploaded file and its metadata."""
    record = storage.get(id)
    if not record:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"File with id '{id}' not found."
        )

    # Delete files on disk
    dest_dir = UPLOAD_DIR / id
    if dest_dir.exists():
        shutil.rmtree(dest_dir, ignore_errors=True)

    storage.delete(id)
    return {"id": id, "status": "DELETED", "message": "File successfully deleted."}
