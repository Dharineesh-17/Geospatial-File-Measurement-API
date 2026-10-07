import os
import zipfile
from pathlib import Path
import geopandas as gpd
from shapely.geometry import Polygon, LineString, Point

BASE_DIR = Path(__file__).resolve().parent.parent
SAMPLES_DIR = BASE_DIR / "samples"
SAMPLES_DIR.mkdir(parents=True, exist_ok=True)


def create_sample_kml():
    """Create a sample KML file containing Polygon, LineString, and Point features."""
    kml_content = """<?xml version="1.0" encoding="UTF-8"?>
<kml xmlns="http://www.opengis.net/kml/2.2">
  <Document>
    <name>Survey Field Project</name>
    <description>Sample geospatial survey containing multiple geometry types</description>
    
    <!-- Polygon: Solar Park Zone -->
    <Placemark id="poly-01">
      <name>Solar Array Alpha</name>
      <description>Perimeter boundary of solar installation alpha</description>
      <ExtendedData>
        <Data name="facility_type"><value>Solar Field</value></Data>
        <Data name="capacity_mw"><value>45</value></Data>
        <Data name="inspector"><value>John Doe</value></Data>
      </ExtendedData>
      <Polygon>
        <extrude>1</extrude>
        <altitudeMode>relativeToGround</altitudeMode>
        <outerBoundaryIs>
          <LinearRing>
            <coordinates>
              77.5900,12.9700,0
              77.5950,12.9700,0
              77.5950,12.9750,0
              77.5900,12.9750,0
              77.5900,12.9700,0
            </coordinates>
          </LinearRing>
        </outerBoundaryIs>
      </Polygon>
    </Placemark>

    <!-- LineString: Power Transmission Line -->
    <Placemark id="line-01">
      <name>Transmission Line Main Grid</name>
      <description>High voltage transmission line connecting to substation</description>
      <ExtendedData>
        <Data name="voltage_kv"><value>132</value></Data>
        <Data name="material"><value>ACSR</value></Data>
      </ExtendedData>
      <LineString>
        <coordinates>
          77.5900,12.9700,0
          77.5925,12.9730,0
          77.5960,12.9740,0
          77.5990,12.9780,0
        </coordinates>
      </LineString>
    </Placemark>

    <!-- Point: Control Station -->
    <Placemark id="pt-01">
      <name>Control Tower Marker</name>
      <description>Telemetry monitoring and control tower</description>
      <ExtendedData>
        <Data name="elevation_m"><value>920</value></Data>
        <Data name="status"><value>ACTIVE</value></Data>
      </ExtendedData>
      <Point>
        <coordinates>77.5920,12.9720,0</coordinates>
      </Point>
    </Placemark>
  </Document>
</kml>
"""
    kml_file = SAMPLES_DIR / "sample_survey.kml"
    kml_file.write_text(kml_content, encoding="utf-8")
    print(f"Created sample KML at {kml_file}")


def create_sample_shapefile_zip():
    """Create a sample Shapefile .zip with polygon parcel geometries."""
    # Shapefile with polygons
    polygons = [
        Polygon([(77.591, 12.971), (77.594, 12.971), (77.594, 12.974), (77.591, 12.974), (77.591, 12.971)]),
        Polygon([(77.585, 12.965), (77.589, 12.965), (77.589, 12.969), (77.585, 12.969), (77.585, 12.965)]),
    ]
    data = {
        "parcel_id": ["P-101", "P-102"],
        "zone_name": ["North Campus", "South Campus"],
        "tax_code": [4201, 4202]
    }
    gdf = gpd.GeoDataFrame(data, geometry=polygons, crs="EPSG:4326")

    temp_shp_dir = SAMPLES_DIR / "temp_shp"
    temp_shp_dir.mkdir(parents=True, exist_ok=True)
    shp_base = temp_shp_dir / "parcels.shp"
    gdf.to_file(str(shp_base))

    # Zip all shapefile files (.shp, .shx, .dbf, .prj, .cpg)
    zip_path = SAMPLES_DIR / "sample_shapefile.zip"
    with zipfile.ZipFile(str(zip_path), "w", zipfile.ZIP_DEFLATED) as zf:
        for file in temp_shp_dir.glob("parcels.*"):
            zf.write(file, arcname=file.name)

    # Clean up temp
    for file in temp_shp_dir.glob("parcels.*"):
        file.unlink()
    temp_shp_dir.rmdir()

    print(f"Created sample Shapefile zip at {zip_path}")


if __name__ == "__main__":
    create_sample_kml()
    create_sample_shapefile_zip()
