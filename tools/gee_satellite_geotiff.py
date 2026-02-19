#!/usr/bin/env python3
import sys, json, urllib.request, zipfile
from pathlib import Path
import ee

def main(jobdir: str, start: str, end: str, out_name: str, scale_m: int):
    jobdir = Path(jobdir)
    geojson_path = jobdir / "basin_wgs84.geojson"
    if not geojson_path.exists():
        raise FileNotFoundError(f"No existe: {geojson_path}")

    ee.Initialize(project="ee-tesishidropablo")

    basin = ee.FeatureCollection(json.loads(geojson_path.read_text()))
    geom = basin.geometry()

    # Sentinel-2 SR armonizado + máscara de nubes simple
    s2 = (ee.ImageCollection("COPERNICUS/S2_SR_HARMONIZED")
          .filterBounds(geom)
          .filterDate(start, end)
          .filter(ee.Filter.lt("CLOUDY_PIXEL_PERCENTAGE", 40)))

    img = s2.median().select(["B4","B3","B2"]).clip(geom)

    # GeoTIFF: se descarga como ZIP con el tif adentro
    url = img.getDownloadURL({
        "region": geom,
        "scale": int(scale_m),
        "format": "GEO_TIFF"
    })

    out_zip = jobdir / f"{out_name}.zip"
    out_tif = jobdir / f"{out_name}.tif"

    urllib.request.urlretrieve(url, out_zip)

    # Extraer el .tif del zip
    with zipfile.ZipFile(out_zip, "r") as z:
        tif_candidates = [n for n in z.namelist() if n.lower().endswith(".tif")]
        if not tif_candidates:
            raise RuntimeError("El ZIP no contiene .tif")
        # toma el primero
        with z.open(tif_candidates[0]) as src, open(out_tif, "wb") as dst:
            dst.write(src.read())

    # Limpieza: deja el tif, borra zip si quieres
    # out_zip.unlink(missing_ok=True)

    print(str(out_tif))

if __name__ == "__main__":
    # args: jobdir start end out_name scale_m
    jobdir = sys.argv[1]
    start  = sys.argv[2]
    end    = sys.argv[3]
    out    = sys.argv[4]
    scale  = int(sys.argv[5]) if len(sys.argv) > 5 else 20
    main(jobdir, start, end, out, scale)
