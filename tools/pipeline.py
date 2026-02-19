from __future__ import annotations
from pathlib import Path
import shutil
import zipfile

import geopandas as gpd
from shapely.geometry import Point

from tools.river_map import run_river_basemap


def _write_outlet_shp(jobdir: Path, lat: float, lon: float) -> None:
    p = jobdir / "outlet_wgs84.shp"
    gdf = gpd.GeoDataFrame(
        {"name": ["outlet"]},
        geometry=[Point(float(lon), float(lat))],
        crs="EPSG:4326",
    )
    gdf.to_file(p)


def _ensure_basin_geojson(jobdir: Path) -> Path | None:
    """Si existe algún geojson de cuenca, lo copia/normaliza a basin_wgs84.geojson."""
    target = jobdir / "basin_wgs84.geojson"
    if target.exists():
        return target

    # Prioridad: nombres que contengan "basin"
    candidates = sorted(jobdir.glob("*basin*.geojson"))
    if not candidates:
        candidates = sorted(jobdir.glob("*.geojson"))

    if not candidates:
        return None

    shutil.copyfile(candidates[0], target)
    return target


def run_all(*, dem_path: str, lat: float, lon: float, out_dir: str, satellite: bool = True) -> dict:
    jobdir = Path(out_dir)
    jobdir.mkdir(parents=True, exist_ok=True)

    dem = Path(dem_path)
    if not dem.exists():
        raise RuntimeError(f"DEM no existe: {dem}")

    # Copia DEM en el jobdir (compat)
    shutil.copyfile(dem, jobdir / "dem.tif")
    shutil.copyfile(dem, jobdir / "dem_clip.tif")

    # Outlet shapefile (tu river_map lo exige)
    _write_outlet_shp(jobdir, lat=lat, lon=lon)

    # Ejecutar pipeline principal
    run_river_basemap(jobdir, zoom=13, dpi=220, stream_quantile=0.92, satellite=bool(satellite))

    # Normalizar basin geojson si existe con otro nombre
    basin_geo = _ensure_basin_geojson(jobdir)

    # Basemap es OPCIONAL: solo si existe basin_geo
    if basin_geo is not None:
        try:
            from tools.basemap_basin import run_basemap_basin_png
            # Tu función actual parece aceptar (jobdir, zoom, dpi)
            run_basemap_basin_png(jobdir, zoom=13, dpi=220)
        except Exception:
            # no tumbamos el run por el basemap
            pass

    # Recolectar outputs existentes
    outputs: dict[str, str] = {}
    for p in sorted(jobdir.iterdir()):
        if p.is_file():
            outputs[p.name] = str(p)

    # Zip entregable
    zip_path = jobdir / "deliverable.zip"
    with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED) as z:
        for p in jobdir.rglob("*"):
            if p.is_file() and p.name != "deliverable.zip":
                z.write(p, arcname=p.relative_to(jobdir))
    outputs["deliverable.zip"] = str(zip_path)

    return outputs
