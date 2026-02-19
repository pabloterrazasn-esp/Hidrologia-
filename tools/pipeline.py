from __future__ import annotations
from pathlib import Path
import shutil
import zipfile

import geopandas as gpd
from shapely.geometry import Point

from tools.river_map import run_river_basemap


def _write_outlet_shp(jobdir: Path, lat: float, lon: float) -> None:
    # Crea outlet_wgs84.shp + .shx + .dbf + .prj (shapefile)
    p = jobdir / "outlet_wgs84.shp"
    gdf = gpd.GeoDataFrame(
        {"name": ["outlet"]},
        geometry=[Point(float(lon), float(lat))],
        crs="EPSG:4326",
    )
    gdf.to_file(p)


def run_all(*, dem_path: str, lat: float, lon: float, out_dir: str, satellite: bool = True) -> dict:
    jobdir = Path(out_dir)
    jobdir.mkdir(parents=True, exist_ok=True)

    dem = Path(dem_path)
    if not dem.exists():
        raise RuntimeError(f"DEM no existe: {dem}")

    # Copia DEM dentro del jobdir con nombres típicos (por compatibilidad)
    # (no sabemos cuál espera river_map internamente, así que ponemos ambos)
    shutil.copyfile(dem, jobdir / "dem.tif")
    shutil.copyfile(dem, jobdir / "dem_clip.tif")

    # Crear outlet shapefile para que _pick_outlet_point(jobdir) lo encuentre
    _write_outlet_shp(jobdir, lat=lat, lon=lon)

    # Ejecutar tu pipeline real
    run_river_basemap(jobdir, zoom=13, dpi=220, stream_quantile=0.92, satellite=bool(satellite))

    # Recolectar outputs (ajusta nombres si tus scripts generan otros)
    outputs: dict[str, str] = {}
    for cand in [
        "satellite_basin_rivers_BLUE_STRONG.png",
        "satellite_basin_rivers_CLASSIFIED.png",
        "basemap_basin.png",
        "basin_wgs84.geojson",
        "mainstem.geojson",
        "dem_clip.tif",
        "dem.tif",
        "outlet_wgs84.shp",
    ]:
        p = jobdir / cand
        if p.exists():
            outputs[cand] = str(p)

    # Zip entregable
    zip_path = jobdir / "deliverable.zip"
    with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED) as z:
        for p in jobdir.rglob("*"):
            if p.is_file() and p.name != "deliverable.zip":
                z.write(p, arcname=p.relative_to(jobdir))
    outputs["deliverable.zip"] = str(zip_path)

    return outputs
