from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field


class GeometrySummary(BaseModel):
    polygons: int = 0
    linestrings: int = 0
    points: int = 0
    others: int = 0
    total: int = 0


class FileUploadResponse(BaseModel):
    id: str = Field(..., description="Unique file identifier")
    filename: str = Field(..., description="Uploaded file name")
    feature_count: int = Field(..., description="Total number of extracted features")
    crs: str = Field(..., description="Detected Coordinate Reference System")
    status: str = Field(..., description="Processing status (e.g., COMPLETED, FAILED)")
    message: Optional[str] = Field(None, description="Informational message")


class FileInfoResponse(BaseModel):
    id: str = Field(..., description="Unique file identifier")
    filename: str = Field(..., description="Uploaded file name")
    feature_count: int = Field(..., description="Total number of extracted features")
    crs: str = Field(..., description="Coordinate Reference System of the file")
    status: str = Field(..., description="Processing status: COMPLETED, FAILED, PROCESSING")
    created_at: Optional[str] = Field(None, description="File upload timestamp")
    file_type: Optional[str] = Field(None, description="Detected format (shapefile or kml)")
    geometry_summary: Optional[GeometrySummary] = Field(None, description="Breakdown of geometry types")


class MeasurementValues(BaseModel):
    area_sq_meters: Optional[float] = Field(None, description="Area in square meters (for Polygon / MultiPolygon)")
    area_sq_km: Optional[float] = Field(None, description="Area in square kilometers")
    area_hectares: Optional[float] = Field(None, description="Area in hectares")
    length_meters: Optional[float] = Field(None, description="Length in meters (for LineString / MultiLineString)")
    length_km: Optional[float] = Field(None, description="Length in kilometers")
    note: Optional[str] = Field(None, description="Graceful handling note for Points or unsupported types")


class FeatureMeasurement(BaseModel):
    feature_id: Any = Field(..., description="Feature ID or Index")
    geometry_type: str = Field(..., description="Geometry type (Polygon, LineString, Point, etc.)")
    original_crs: str = Field(..., description="Original CRS of the feature")
    projected_crs: Optional[str] = Field(None, description="Projected CRS used for metric calculation")
    measurements: MeasurementValues = Field(..., description="Calculated measurement values")
    properties: Dict[str, Any] = Field(default_factory=dict, description="Attributes and properties of feature")
    geometry: Optional[Dict[str, Any]] = Field(None, description="GeoJSON geometry representation")


class MeasurementSummary(BaseModel):
    total_polygon_area_sq_meters: float = 0.0
    total_polygon_area_sq_km: float = 0.0
    total_linestring_length_meters: float = 0.0
    total_linestring_length_km: float = 0.0
    supported_feature_count: int = 0
    unsupported_feature_count: int = 0


class FileMeasurementsResponse(BaseModel):
    id: str = Field(..., description="Unique file identifier")
    filename: str = Field(..., description="Uploaded file name")
    crs: str = Field(..., description="Source coordinate reference system")
    projected_crs: Optional[str] = Field(None, description="Primary projected CRS applied")
    feature_count: int = Field(..., description="Total features count")
    summary: MeasurementSummary = Field(..., description="Aggregate measurement statistics")
    features: List[FeatureMeasurement] = Field(..., description="List of feature measurements")
