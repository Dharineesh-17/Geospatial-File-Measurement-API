import math
from typing import Optional, Tuple, Dict, Any
import shapely
from shapely.geometry.base import BaseGeometry
import pyproj
from pyproj import CRS, Transformer


def determine_utm_crs(lon: float, lat: float) -> str:
    """Determine the optimal UTM projection EPSG code for a given longitude and latitude.
    
    Formula:
    utm_zone = int((lon + 180) / 6) + 1
    EPSG: 32600 + zone for Northern hemisphere, 32700 + zone for Southern hemisphere.
    """
    # Clamp coordinates to valid geographic bounds
    lon = max(-180.0, min(180.0, lon))
    lat = max(-89.9, min(89.9, lat))

    utm_zone = int((lon + 180.0) / 6.0) + 1
    if utm_zone > 60:
        utm_zone = 60
    elif utm_zone < 1:
        utm_zone = 1

    if lat >= 0:
        epsg_code = 32600 + utm_zone
    else:
        epsg_code = 32700 + utm_zone

    return f"EPSG:{epsg_code}"


def get_projected_crs_for_geometry(geom: BaseGeometry, source_crs_str: str) -> str:
    """Given a shapely geometry and its source CRS, returns an appropriate projected CRS."""
    try:
        source_crs = CRS.from_user_input(source_crs_str)
        if source_crs.is_projected:
            return source_crs.to_string()
    except Exception:
        pass

    # Source is geographic or unspecified - find centroid
    try:
        centroid = geom.centroid
        if not centroid.is_empty:
            lon, lat = centroid.x, centroid.y
            return determine_utm_crs(lon, lat)
    except Exception:
        pass

    # Fallback to World Cylindrical Equal Area or WGS 84 / UTM Zone 31N
    return "EPSG:3857"


def transform_geometry(geom: BaseGeometry, from_crs_str: str, to_crs_str: str) -> Optional[BaseGeometry]:
    """Transform geometry from source CRS to target projected CRS using pyproj and modern Shapely 2.x."""
    try:
        if from_crs_str.upper() == to_crs_str.upper():
            return geom

        from_crs = CRS.from_user_input(from_crs_str)
        to_crs = CRS.from_user_input(to_crs_str)
        project_transformer = Transformer.from_crs(from_crs, to_crs, always_xy=True)

        import numpy as np

        def _reproject(coords):
            x, y = project_transformer.transform(coords[:, 0], coords[:, 1])
            if coords.shape[1] >= 3:
                return np.column_stack((x, y, coords[:, 2]))
            return np.column_stack((x, y))

        return shapely.transform(geom, _reproject)
    except Exception:
        return None


def calculate_feature_measurements(
    geom: Optional[BaseGeometry],
    source_crs_str: str,
    target_projected_crs_str: Optional[str] = None
) -> Dict[str, Any]:
    """Calculates measurements for a feature geometry gracefully.
    
    Returns a dictionary with:
    - measurements: dict (area_sq_meters, area_sq_km, area_hectares, length_meters, length_km, note)
    - projected_crs: str or None
    - error: str or None
    """
    if geom is None or geom.is_empty:
        return {
            "measurements": {
                "area_sq_meters": None,
                "area_sq_km": None,
                "area_hectares": None,
                "length_meters": None,
                "length_km": None,
                "note": "Geometry is empty or null."
            },
            "projected_crs": None
        }

    geom_type = geom.geom_type

    # Points do not require measurements per spec
    if geom_type in ("Point", "MultiPoint"):
        return {
            "measurements": {
                "area_sq_meters": None,
                "area_sq_km": None,
                "area_hectares": None,
                "length_meters": None,
                "length_km": None,
                "note": "Point geometry has no area or length measurement."
            },
            "projected_crs": None
        }

    # Only Polygon and LineString (and their Multi variants) are supported for measurement
    if geom_type not in ("Polygon", "MultiPolygon", "LineString", "MultiLineString"):
        return {
            "measurements": {
                "area_sq_meters": None,
                "area_sq_km": None,
                "area_hectares": None,
                "length_meters": None,
                "length_km": None,
                "note": f"Geometry type '{geom_type}' is not supported for measurement calculation."
            },
            "projected_crs": None
        }

    # Select projected CRS
    projected_crs = target_projected_crs_str or get_projected_crs_for_geometry(geom, source_crs_str)

    # Transform geometry to projected CRS
    transformed_geom = transform_geometry(geom, source_crs_str, projected_crs)
    if transformed_geom is None or transformed_geom.is_empty:
        return {
            "measurements": {
                "area_sq_meters": None,
                "area_sq_km": None,
                "area_hectares": None,
                "length_meters": None,
                "length_km": None,
                "note": f"Could not project geometry from {source_crs_str} to {projected_crs}."
            },
            "projected_crs": projected_crs
        }

    if geom_type in ("Polygon", "MultiPolygon"):
        area_m2 = round(float(transformed_geom.area), 4)
        area_km2 = round(area_m2 / 1_000_000.0, 6)
        area_ha = round(area_m2 / 10_000.0, 4)
        return {
            "measurements": {
                "area_sq_meters": area_m2,
                "area_sq_km": area_km2,
                "area_hectares": area_ha,
                "length_meters": None,
                "length_km": None,
                "note": None
            },
            "projected_crs": projected_crs
        }

    elif geom_type in ("LineString", "MultiLineString"):
        length_m = round(float(transformed_geom.length), 4)
        length_km = round(length_m / 1_000.0, 6)
        return {
            "measurements": {
                "area_sq_meters": None,
                "area_sq_km": None,
                "area_hectares": None,
                "length_meters": length_m,
                "length_km": length_km,
                "note": None
            },
            "projected_crs": projected_crs
        }

    return {
        "measurements": {
            "area_sq_meters": None,
            "area_sq_km": None,
            "area_hectares": None,
            "length_meters": None,
            "length_km": None,
            "note": f"Geometry type '{geom_type}' is unsupported."
        },
        "projected_crs": projected_crs
    }
