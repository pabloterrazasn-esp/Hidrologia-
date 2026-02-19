import json, sys
import os
import ee
import requests
from pathlib import Path

def load_geom_from_geojson(path: Path):
    gj = json.loads(path.read_text())
    # basin_wgs84.geojson es FeatureCollection o Feature
    if gj.get("type") == "FeatureCollection":
        geom = gj["features"][0]["geometry"]
    elif gj.get("type") == "Feature":
        geom = gj["geometry"]
    else:
        geom = gj
    return ee.Geometry(geom)

def s2_cloudmask(img):
    # S2 SR Harmonized: QA60 (nubes)
    qa = img.select("QA60")
    cloud = qa.bitwiseAnd(1 << 10).neq(0)
    cirrus = qa.bitwiseAnd(1 << 11).neq(0)
    mask = cloud.Or(cirrus).Not()
    return img.updateMask(mask)

def main(jobdir: str, start: str, end: str, out_name: str, dims: int = 2048):
    project = os.environ.get('EE_PROJECT') or os.environ.get('GOOGLE_CLOUD_PROJECT')
    if not project:
        raise RuntimeError('Falta EE_PROJECT. Ponlo en terranava_app/.env (ej: EE_PROJECT=ee-tesishidropablo)')
    ee.Initialize(project=project)

    job = Path(jobdir)
    basin_geojson = job / "basin_wgs84.geojson"
    out_png = job / out_name

    geom = load_geom_from_geojson(basin_geojson)

    # Sentinel-2 SR harmonized, nube básica, compuesto median
    col = (ee.ImageCollection("COPERNICUS/S2_SR_HARMONIZED")
           .filterDate(start, end)
           .filterBounds(geom)
           .filter(ee.Filter.lt("CLOUDY_PIXEL_PERCENTAGE", 35))
           .map(s2_cloudmask))

    img = col.median().clip(geom)

    # Visualización “natural color”
    vis = {"bands": ["B4","B3","B2"], "min": 0, "max": 3000}

    # Borde de la cuenca (pintado encima)
    outline = ee.Image().byte().paint(geom, 1, 3)  # width 3px
    rgb = img.visualize(**vis).blend(outline.visualize(min=0, max=1))

    # ThumbURL sí permite PNG (a diferencia de Export.image)
    url = rgb.getThumbURL({
        "region": geom,
        "dimensions": dims,
        "format": "png"
    })

    r = requests.get(url, timeout=180)
    r.raise_for_status()
    out_png.write_bytes(r.content)

    print(str(out_png))

if __name__ == "__main__":
    # args: jobdir start end out_name dims
    jobdir = sys.argv[1]
    start = sys.argv[2] if len(sys.argv) > 2 else "2024-01-01"
    end   = sys.argv[3] if len(sys.argv) > 3 else "2025-12-31"
    out_name = sys.argv[4] if len(sys.argv) > 4 else "satellite_s2.png"
    dims = int(sys.argv[5]) if len(sys.argv) > 5 else 2048
    main(jobdir, start, end, out_name, dims)
