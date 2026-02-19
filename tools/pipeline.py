from __future__ import annotations
from pathlib import Path
import shutil
import traceback

def run_all(*, dem_path: str, lat: float, lon: float, out_dir: str) -> dict:
    """
    Ejecuta el pipeline completo y devuelve rutas de archivos generados.
    Requisitos: dem_path existe. out_dir existe.
    """
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)

    dem = Path(dem_path)
    if not dem.exists():
        raise RuntimeError(f"DEM no existe: {dem}")

    # Copia DEM al out_dir para trazabilidad
    dem_local = out / "dem.tif"
    try:
        if dem.resolve() != dem_local.resolve():
            shutil.copyfile(dem, dem_local)
    except Exception:
        # no es fatal
        pass

    outputs: dict[str, str] = {}

    # 1) Delineación + ríos (depende de tu river_map.py)
    # Intentamos detectar una función "main" o "run_*"
    try:
        from tools import river_map  # type: ignore

        # Preferencias de nombres (si existen)
        candidates = [
            "run_all",
            "run",
            "run_river_map",
            "make_river_map",
            "generate",
            "main",
        ]

        fn = None
        for name in candidates:
            if hasattr(river_map, name) and callable(getattr(river_map, name)):
                fn = getattr(river_map, name)
                break

        if fn is None:
            raise RuntimeError("No encontré una función ejecutable en tools/river_map.py (esperaba run/main/etc.)")

        # Intento de llamada con firma flexible
        try:
            res = fn(dem_path=str(dem_local), lat=lat, lon=lon, out_dir=str(out))
        except TypeError:
            # fallback: algunos scripts usan dem, pour point, etc.
            res = fn(str(dem_local), lat, lon, str(out))

        if isinstance(res, dict):
            # si tu función devuelve rutas
            for k, v in res.items():
                if isinstance(v, (str, Path)):
                    outputs[str(k)] = str(v)
        # Si tu función escribe archivos con nombres fijos, los buscamos:
        for cand in [
            "satellite_basin_rivers_BLUE_STRONG.png",
            "satellite_basin_rivers_CLASSIFIED.png",
            "basin.png",
            "rivers.png",
            "basin_wgs84.geojson",
            "mainstem.geojson",
        ]:
            p = out / cand
            if p.exists():
                outputs[cand] = str(p)

    except Exception as e:
        # Error controlado (esto luego sale en /run como JSON)
        raise RuntimeError("Fallo en river_map pipeline: " + str(e) + "\n" + traceback.format_exc())

    # 2) Basemap opcional (si lo usas)
    try:
        from tools.basemap_basin import run_basemap_basin_png  # type: ignore

        # Si existe basin geojson, hacemos un basemap simple
        basin_geo = out / "basin_wgs84.geojson"
        if basin_geo.exists():
            out_png = out / "basemap_basin.png"
            try:
                run_basemap_basin_png(str(basin_geo), str(out_png))
                if out_png.exists():
                    outputs["basemap_basin.png"] = str(out_png)
            except TypeError:
                # por si tu firma es distinta
                run_basemap_basin_png(basin_geo, out_png)
                if out_png.exists():
                    outputs["basemap_basin.png"] = str(out_png)
    except Exception:
        # Basemap es opcional: no tumbamos
        pass

    # 3) ZIP opcional (si lo quieres ya)
    try:
        import zipfile
        zip_path = out / "deliverable.zip"
        with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED) as z:
            for p in out.rglob("*"):
                if p.is_file() and p.name != "deliverable.zip":
                    z.write(p, arcname=p.relative_to(out))
        outputs["deliverable.zip"] = str(zip_path)
    except Exception:
        pass

    # Para /run, devolvemos rutas absolutas; api.py ya las transforma a /results/...
    return outputs
