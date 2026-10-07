import pytest
from pathlib import Path
from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)

BASE_DIR = Path(__file__).resolve().parent.parent
SAMPLES_DIR = BASE_DIR / "samples"
KML_SAMPLE = SAMPLES_DIR / "sample_survey.kml"
SHP_SAMPLE = SAMPLES_DIR / "sample_shapefile.zip"


def test_health_check():
    """Verify health endpoint response."""
    response = client.get("/api/health/")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "healthy"
    assert "Geospatial File Measurement API" in data["service"]


def test_dashboard_ui():
    """Verify web dashboard loads."""
    response = client.get("/")
    assert response.status_code == 200
    assert "Geospatial File Measurement API" in response.text


def test_upload_kml_file():
    """Upload and process a KML file with Polygon, LineString, and Point."""
    assert KML_SAMPLE.exists(), f"Sample KML not found at {KML_SAMPLE}"

    with open(KML_SAMPLE, "rb") as f:
        response = client.post(
            "/api/files/",
            files={"file": ("sample_survey.kml", f, "application/vnd.google-earth.kml+xml")}
        )

    assert response.status_code == 201
    data = response.json()
    assert "id" in data
    assert data["filename"] == "sample_survey.kml"
    assert data["feature_count"] == 3
    assert data["status"] == "COMPLETED"
    assert "EPSG:4326" in data["crs"]

    file_id = data["id"]

    # Test GET /api/files/{id}/
    info_resp = client.get(f"/api/files/{file_id}/")
    assert info_resp.status_code == 200
    info_data = info_resp.json()
    assert info_data["id"] == file_id
    assert info_data["filename"] == "sample_survey.kml"
    assert info_data["feature_count"] == 3
    assert info_data["status"] == "COMPLETED"
    assert info_data["geometry_summary"]["polygons"] == 1
    assert info_data["geometry_summary"]["linestrings"] == 1
    assert info_data["geometry_summary"]["points"] == 1

    # Test GET /api/files/{id}/measurements/
    meas_resp = client.get(f"/api/files/{file_id}/measurements/")
    assert meas_resp.status_code == 200
    meas_data = meas_resp.json()
    assert meas_data["id"] == file_id
    assert meas_data["feature_count"] == 3
    assert meas_data["projected_crs"] is not None
    assert meas_data["summary"]["supported_feature_count"] == 3

    features = meas_data["features"]
    assert len(features) == 3

    # Check Polygon feature measurements
    poly_feat = next(f for f in features if f["geometry_type"] == "Polygon")
    assert poly_feat["measurements"]["area_sq_meters"] is not None
    assert poly_feat["measurements"]["area_sq_meters"] > 0
    assert poly_feat["measurements"]["area_sq_km"] is not None
    assert poly_feat["measurements"]["area_hectares"] is not None
    assert poly_feat["measurements"]["length_meters"] is None
    assert "Solar Array Alpha" in poly_feat["properties"].get("name", "")

    # Check LineString feature measurements
    line_feat = next(f for f in features if f["geometry_type"] == "LineString")
    assert line_feat["measurements"]["length_meters"] is not None
    assert line_feat["measurements"]["length_meters"] > 0
    assert line_feat["measurements"]["length_km"] is not None
    assert line_feat["measurements"]["area_sq_meters"] is None

    # Check Point feature graceful handling
    point_feat = next(f for f in features if f["geometry_type"] == "Point")
    assert point_feat["measurements"]["area_sq_meters"] is None
    assert point_feat["measurements"]["length_meters"] is None
    assert point_feat["measurements"]["note"] is not None

    # Test GET /api/files/{id}/geojson
    geo_resp = client.get(f"/api/files/{file_id}/geojson")
    assert geo_resp.status_code == 200
    geo_data = geo_resp.json()
    assert geo_data["type"] == "FeatureCollection"
    assert len(geo_data["features"]) == 3


def test_upload_shapefile_zip():
    """Upload and process a zipped Shapefile (.zip)."""
    assert SHP_SAMPLE.exists(), f"Sample Shapefile not found at {SHP_SAMPLE}"

    with open(SHP_SAMPLE, "rb") as f:
        response = client.post(
            "/api/files/",
            files={"file": ("sample_shapefile.zip", f, "application/zip")}
        )

    assert response.status_code == 201
    data = response.json()
    assert data["filename"] == "sample_shapefile.zip"
    assert data["feature_count"] == 2
    assert data["status"] == "COMPLETED"

    file_id = data["id"]

    # Verify measurements
    meas_resp = client.get(f"/api/files/{file_id}/measurements/")
    assert meas_resp.status_code == 200
    meas_data = meas_resp.json()
    assert meas_data["summary"]["total_polygon_area_sq_meters"] > 0
    for feat in meas_data["features"]:
        assert feat["geometry_type"] == "Polygon"
        assert feat["measurements"]["area_sq_meters"] > 0
        assert feat["projected_crs"] is not None


def test_unsupported_file_extension():
    """Reject unsupported file extensions with 400 Bad Request."""
    response = client.post(
        "/api/files/",
        files={"file": ("unsupported.txt", b"plain text", "text/plain")}
    )
    assert response.status_code == 400
    assert "Unsupported file format" in response.json()["detail"]


def test_file_not_found():
    """Return 404 for non-existent file queries."""
    res_info = client.get("/api/files/fakeid999/")
    assert res_info.status_code == 404

    res_meas = client.get("/api/files/fakeid999/measurements/")
    assert res_meas.status_code == 404


def test_delete_file():
    """Upload a file and delete it."""
    with open(KML_SAMPLE, "rb") as f:
        upload_res = client.post(
            "/api/files/",
            files={"file": ("temp_to_delete.kml", f, "application/vnd.google-earth.kml+xml")}
        )
    file_id = upload_res.json()["id"]

    # Delete
    del_res = client.delete(f"/api/files/{file_id}/")
    assert del_res.status_code == 200
    assert del_res.json()["status"] == "DELETED"

    # Confirm gone
    get_res = client.get(f"/api/files/{file_id}/")
    assert get_res.status_code == 404


def test_invalid_shapefile_zip_without_shp():
    """Upload zip without .shp file should return 400."""
    import io
    import zipfile
    bio = io.BytesIO()
    with zipfile.ZipFile(bio, "w") as zf:
        zf.writestr("notes.txt", "No shapefile here")
    bio.seek(0)

    res = client.post(
        "/api/files/",
        files={"file": ("invalid.zip", bio.getvalue(), "application/zip")}
    )
    assert res.status_code == 400
    assert "No .shp file found" in res.json()["detail"]


def test_unsupported_geometry_handled_gracefully():
    """Test calculate_feature_measurements gracefully handles unsupported geometry types."""
    from app.services.measurement import calculate_feature_measurements
    from shapely.geometry import GeometryCollection, Point

    coll = GeometryCollection([Point(0, 0)])
    result = calculate_feature_measurements(coll, "EPSG:4326")
    assert result["measurements"]["area_sq_meters"] is None
    assert result["measurements"]["length_meters"] is None
    assert "not supported" in result["measurements"]["note"]


def test_list_files():
    """Verify listing files."""
    res = client.get("/api/files/")
    assert res.status_code == 200
    assert isinstance(res.json(), list)

