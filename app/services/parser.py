import os
import zipfile
import tempfile
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import List, Dict, Any, Tuple, Optional
import numpy as np
import pandas as pd
import shapely
from shapely.geometry import shape, mapping, Polygon, LineString, Point, MultiPolygon, MultiLineString, MultiPoint
import geopandas as gpd

from app.services.measurement import calculate_feature_measurements, determine_utm_crs


def sanitize_value(val: Any) -> Any:
    """Sanitize properties to ensure JSON serializability (handle NaNs, NaTs, numpy types)."""
    if pd.isna(val) or val is None:
        return None
    if isinstance(val, (np.integer, int)):
        return int(val)
    if isinstance(val, (np.floating, float)):
        if np.isnan(val) or np.isinf(val):
            return None
        return float(val)
    if isinstance(val, (np.bool_, bool)):
        return bool(val)
    if isinstance(val, (np.ndarray, list)):
        return [sanitize_value(x) for x in val]
    if isinstance(val, dict):
        return {str(k): sanitize_value(v) for k, v in val.items()}
    return str(val)


def parse_kml_xml(kml_path: Path) -> List[Dict[str, Any]]:
    """Robust built-in XML parser for KML files (works independently of GDAL/Fiona drivers)."""
    tree = ET.parse(str(kml_path))
    root = tree.getroot()

    # KML namespaces
    ns = ""
    if root.tag.startswith("{"):
        ns = root.tag.split("}")[0] + "}"

    features = []
    placemarks = root.findall(f".//{ns}Placemark")

    for idx, pm in enumerate(placemarks):
        # Extract properties
        name_el = pm.find(f"{ns}name")
        desc_el = pm.find(f"{ns}description")
        properties: Dict[str, Any] = {}
        if name_el is not None and name_el.text:
            properties["name"] = name_el.text.strip()
        if desc_el is not None and desc_el.text:
            properties["description"] = desc_el.text.strip()

        # ExtendedData / SimpleData
        for data in pm.findall(f".//{ns}Data"):
            key = data.attrib.get("name")
            val_el = data.find(f"{ns}value")
            if key and val_el is not None and val_el.text:
                properties[key] = val_el.text.strip()
        for sdata in pm.findall(f".//{ns}SimpleData"):
            key = sdata.attrib.get("name")
            if key and sdata.text:
                properties[key] = sdata.text.strip()

        # Parse geometry
        geom = None
        # 1. Polygon
        poly_el = pm.find(f".//{ns}Polygon")
        if poly_el is not None:
            geom = _parse_kml_polygon(poly_el, ns)

        # 2. LineString
        if geom is None:
            ls_el = pm.find(f".//{ns}LineString")
            if ls_el is not None:
                geom = _parse_kml_linestring(ls_el, ns)

        # 3. Point
        if geom is None:
            pt_el = pm.find(f".//{ns}Point")
            if pt_el is not None:
                geom = _parse_kml_point(pt_el, ns)

        # 4. MultiGeometry
        if geom is None:
            mg_el = pm.find(f".//{ns}MultiGeometry")
            if mg_el is not None:
                geom = _parse_kml_multigeometry(mg_el, ns)

        features.append({
            "feature_id": pm.attrib.get("id", idx),
            "shapely_geom": geom,
            "crs": "EPSG:4326",
            "properties": properties
        })

    return features


def _parse_coords(coord_text: str) -> List[Tuple[float, float]]:
    """Parse coordinate string from KML into [(lon, lat), ...]."""
    coords = []
    for item in coord_text.strip().split():
        parts = item.split(",")
        if len(parts) >= 2:
            try:
                lon = float(parts[0])
                lat = float(parts[1])
                coords.append((lon, lat))
            except ValueError:
                continue
    return coords


def _parse_kml_polygon(el: ET.Element, ns: str) -> Optional[Polygon]:
    coord_el = el.find(f".//{ns}outerBoundaryIs//{ns}coordinates")
    if coord_el is None or not coord_el.text:
        return None
    shell = _parse_coords(coord_el.text)
    if len(shell) < 3:
        return None

    holes = []
    for inner in el.findall(f".//{ns}innerBoundaryIs"):
        in_coord = inner.find(f".//{ns}coordinates")
        if in_coord is not None and in_coord.text:
            hole_coords = _parse_coords(in_coord.text)
            if len(hole_coords) >= 3:
                holes.append(hole_coords)

    try:
        return Polygon(shell, holes)
    except Exception:
        return None


def _parse_kml_linestring(el: ET.Element, ns: str) -> Optional[LineString]:
    coord_el = el.find(f".//{ns}coordinates")
    if coord_el is None or not coord_el.text:
        return None
    coords = _parse_coords(coord_el.text)
    if len(coords) < 2:
        return None
    try:
        return LineString(coords)
    except Exception:
        return None


def _parse_kml_point(el: ET.Element, ns: str) -> Optional[Point]:
    coord_el = el.find(f".//{ns}coordinates")
    if coord_el is None or not coord_el.text:
        return None
    coords = _parse_coords(coord_el.text)
    if not coords:
        return None
    try:
        return Point(coords[0])
    except Exception:
        return None


def _parse_kml_multigeometry(el: ET.Element, ns: str) -> Optional[Any]:
    geoms = []
    for p in el.findall(f".//{ns}Polygon"):
        g = _parse_kml_polygon(p, ns)
        if g: geoms.append(g)
    for ls in el.findall(f".//{ns}LineString"):
        g = _parse_kml_linestring(ls, ns)
        if g: geoms.append(g)
    for pt in el.findall(f".//{ns}Point"):
        g = _parse_kml_point(pt, ns)
        if g: geoms.append(g)

    if not geoms:
        return None
    if all(isinstance(g, Polygon) for g in geoms):
        return MultiPolygon(geoms)
    if all(isinstance(g, LineString) for g in geoms):
        return MultiLineString(geoms)
    if all(isinstance(g, Point) for g in geoms):
        return MultiPoint(geoms)
    return shapely.geometry.GeometryCollection(geoms)


def extract_features_from_shapefile(zip_path: Path) -> Tuple[List[Dict[str, Any]], str]:
    """Extracts Shapefile from a zip archive and reads its features."""
    extract_dir = zip_path.parent / f"extracted_{zip_path.stem}"
    extract_dir.mkdir(parents=True, exist_ok=True)

    with zipfile.ZipFile(str(zip_path), "r") as zf:
        # Check against zip slip vulnerability
        for member in zf.namelist():
            target_path = (extract_dir / member).resolve()
            if not str(target_path).startswith(str(extract_dir.resolve())):
                raise ValueError("Zip archive contains invalid directory traversal paths.")
        zf.extractall(str(extract_dir))

    # Find .shp file
    shp_files = list(extract_dir.rglob("*.shp"))
    if not shp_files:
        raise ValueError("No .shp file found inside the uploaded zip archive.")

    shp_path = shp_files[0]
    gdf = gpd.read_file(str(shp_path))

    detected_crs = "EPSG:4326"
    if gdf.crs is not None:
        try:
            detected_crs = gdf.crs.to_string()
        except Exception:
            detected_crs = str(gdf.crs)

    features = []
    for idx, row in gdf.iterrows():
        geom = row.geometry
        props = {
            col: sanitize_value(row[col])
            for col in gdf.columns
            if col != gdf.geometry.name
        }
        features.append({
            "feature_id": idx,
            "shapely_geom": geom,
            "crs": detected_crs,
            "properties": props
        })

    return features, detected_crs


def extract_features_from_kml(kml_path: Path) -> Tuple[List[Dict[str, Any]], str]:
    """Extracts features from a KML file using Fiona or native XML fallback."""
    try:
        # Attempt via Fiona / GeoPandas if drivers supported
        import fiona
        if "KML" in fiona.supported_drivers:
            gdf = gpd.read_file(str(kml_path), driver="KML")
            detected_crs = gdf.crs.to_string() if gdf.crs else "EPSG:4326"
            features = []
            for idx, row in gdf.iterrows():
                props = {col: sanitize_value(row[col]) for col in gdf.columns if col != gdf.geometry.name}
                features.append({
                    "feature_id": idx,
                    "shapely_geom": row.geometry,
                    "crs": detected_crs,
                    "properties": props
                })
            return features, detected_crs
    except Exception:
        pass

    # Use native robust XML parser
    features = parse_kml_xml(kml_path)
    return features, "EPSG:4326"


def process_geospatial_file(file_path: Path, filename: str) -> Dict[str, Any]:
    """Processes geospatial file (.zip shapefile or .kml) and computes measurements."""
    lower_name = filename.lower()
    if lower_name.endswith(".zip"):
        features_raw, detected_crs = extract_features_from_shapefile(file_path)
        file_type = "shapefile"
    elif lower_name.endswith(".kml"):
        features_raw, detected_crs = extract_features_from_kml(file_path)
        file_type = "kml"
    else:
        raise ValueError("Unsupported file format. Please upload a .zip (Shapefile) or .kml file.")

    # Process features and calculate measurements
    processed_features = []
    total_poly_area_m2 = 0.0
    total_line_len_m = 0.0
    poly_count = 0
    line_count = 0
    point_count = 0
    other_count = 0
    supported_count = 0
    unsupported_count = 0
    primary_projected_crs = None

    for raw in features_raw:
        fid = raw["feature_id"]
        geom = raw["shapely_geom"]
        fcrs = raw["crs"]
        props = raw["properties"]

        if geom is None or geom.is_empty:
            geom_type = "Unknown"
            geojson = None
        else:
            geom_type = geom.geom_type
            geojson = mapping(geom)

        # Track geometry types
        if geom_type in ("Polygon", "MultiPolygon"):
            poly_count += 1
            supported_count += 1
        elif geom_type in ("LineString", "MultiLineString"):
            line_count += 1
            supported_count += 1
        elif geom_type in ("Point", "MultiPoint"):
            point_count += 1
            supported_count += 1
        else:
            other_count += 1
            unsupported_count += 1

        calc_res = calculate_feature_measurements(geom, fcrs)
        measurements = calc_res["measurements"]
        proj_crs = calc_res["projected_crs"]
        if proj_crs and not primary_projected_crs:
            primary_projected_crs = proj_crs

        if measurements.get("area_sq_meters") is not None:
            total_poly_area_m2 += measurements["area_sq_meters"]
        if measurements.get("length_meters") is not None:
            total_line_len_m += measurements["length_meters"]

        processed_features.append({
            "feature_id": fid,
            "geometry_type": geom_type,
            "original_crs": fcrs,
            "projected_crs": proj_crs,
            "measurements": measurements,
            "properties": props,
            "geometry": geojson
        })

    summary = {
        "total_polygon_area_sq_meters": round(total_poly_area_m2, 4),
        "total_polygon_area_sq_km": round(total_poly_area_m2 / 1_000_000.0, 6),
        "total_linestring_length_meters": round(total_line_len_m, 4),
        "total_linestring_length_km": round(total_line_len_m / 1_000.0, 6),
        "supported_feature_count": supported_count,
        "unsupported_feature_count": unsupported_count
    }

    geometry_summary = {
        "polygons": poly_count,
        "linestrings": line_count,
        "points": point_count,
        "others": other_count,
        "total": len(processed_features)
    }

    return {
        "filename": filename,
        "file_type": file_type,
        "feature_count": len(processed_features),
        "crs": detected_crs,
        "projected_crs": primary_projected_crs or "N/A",
        "status": "COMPLETED",
        "geometry_summary": geometry_summary,
        "summary": summary,
        "features": processed_features
    }
