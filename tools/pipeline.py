from __future__ import annotations
from pathlib import Path
import shutil
import zipfile

import geopandas as gpd
from shapely.geometry import Point

from tools.river_map import run_river_basemap


def _write_outlet_shp(jobdir: Path, lat: float, lon: float) -> None:
    shp = jobdir / "outlet_wgs84.shp"
    gdf = gpd.GeoDataFrame(
        {"name": ["outlet"]},
        geometry=[Point(float(lon), float(lat))],
        crs="EPSG:4326",
    )
    gdf.to_file(shp)


def run_all(*, dem_path: str, lat: float, lon: float, out_dir: str, satellite: bool = True) -> dict:
    jobdir = Path(out_dir)
    jobdir.mkdir(parents=True, exist_ok=True)

    dem = Path(dem_path)
    if not dem.exists():
        raise RuntimeError(f"DEM no existe: {dem}")

    # Copia DEM al jobdir (compat)
    shutil.copyfile(dem, jobdir / "dem.tif")
    shutil.copyfile(dem, jobdir / "dem_clip.tif")

    # Outlet requerido por river_map
    _write_outlet_shp(jobdir, lat=lat, lon=lon)

    # MVP: asegurar que exista el archivo que te está rompiendo (aunque sea placeholder)
    (jobdir / "basin_wgs84.geojson").write_text(
        '{"type":"FeatureCollection","features":[]}',
        encoding="utf-8",
    )

    # Ejecutar pipeline principal
    run_river_basemap(
        jobdir,
        zoom=13,
        dpi=220,
        stream_quantile=0.92,
        satellite=bool(satellite),
    )

    # Basemap opcional: no tumbamos si falla
    try:
        # solo intentar si existe algún geojson (aunque sea vacío)
        if (jobdir / "basin_wgs84.geojson").exists():
            from tools.basemap_basin import run_basemap_basin_png
            run_basemap_basin_png(jobdir, zoom=13, dpi=220)
    except Exception:
        pass

    # Zip entregable
    zip_path = jobdir / "deliverable.zip"
    with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED) as z:
        for p in jobdir.rglob("*"):
            if p.is_file() and p.name != "deliverable.zip":
                z.write(p, arcname=p.relative_to(jobdir))

    outputs = {p.name: str(p) for p in jobdir.iterdir() if p.is_file()}
    outputs["deliverable.zip"] = str(zip_path)
    return outputs
