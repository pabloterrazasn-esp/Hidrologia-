import json, re, subprocess
from pathlib import Path

def sh(cmd):
    p = subprocess.run(cmd, shell=True, text=True, capture_output=True)
    if p.returncode != 0:
        raise RuntimeError(p.stderr or p.stdout or cmd)
    return p.stdout

def gdal_stats(path: Path):
    txt = sh(f'gdalinfo -stats "{path}"')
    def grab(k):
        m = re.search(rf"STATISTICS_{k}=([0-9\.\-eE]+)", txt)
        return float(m.group(1)) if m else None
    return {"min":grab("MINIMUM"),"max":grab("MAXIMUM"),"mean":grab("MEAN"),"std":grab("STDDEV")}

def main(jobdir: str, dem_path: str, epsg: str):
    job = Path(jobdir)

    # DEM clip UTM (metros) con la cuenca en WGS84
    dem_clip_utm = job / "dem_clip_utm.tif"
    slope_deg_utm = job / "slope_deg_utm.tif"

    sh(f'rm -f "{dem_clip_utm}" "{slope_deg_utm}" "{job/"report_B.json"}" "{job/"report_B.csv"}"')

    sh(
        f'gdalwarp -overwrite -t_srs {epsg} '
        f'-cutline "{job/"basin_wgs84.geojson"}" -crop_to_cutline -dstnodata -9999 '
        f'"{dem_path}" "{dem_clip_utm}"'
    )
    sh(f'gdaldem slope "{dem_clip_utm}" "{slope_deg_utm}" -compute_edges')

    # Área/perímetro desde basin_utm.shp (métrico)
    shp = job / "basin_utm.shp"
    sql = 'SELECT ST_Area(geometry) AS area_m2, ST_Perimeter(geometry) AS perim_m FROM basin_utm'
    out = subprocess.check_output(
        ["ogrinfo","-dialect","sqlite","-al","-geom=NO",str(shp),"-sql",sql],
        text=True
    )

    area_m2 = None
    perim_m = None
    for ln in out.splitlines():
        if "area_m2" in ln and "=" in ln:
            try: area_m2 = float(ln.split("=")[-1].strip())
            except: pass
        if "perim_m" in ln and "=" in ln:
            try: perim_m = float(ln.split("=")[-1].strip())
            except: pass
    if area_m2 is None or perim_m is None:
        raise RuntimeError("No pude leer area/perim desde ogrinfo.")

    elev = gdal_stats(dem_clip_utm)
    slope = gdal_stats(slope_deg_utm)

    report = {
        "basin_name": "TerraNava basin (by picked point)",
        "geometry": {
            "area_km2": round(area_m2/1e6, 4),
            "perimeter_km": round(perim_m/1000, 4),
            "crs_area": epsg
        },
        "elevation_m": elev,
        "slope_deg": slope,
        "files": {
            "basin_wgs84_geojson": str(job / "basin_wgs84.geojson"),
            "basin_utm_shp": str(job / "basin_utm.shp"),
            "dem_clip_utm": str(dem_clip_utm),
            "slope_deg_utm": str(slope_deg_utm)
        }
    }

    (job / "report_B.json").write_text(json.dumps(report, indent=2))
    (job / "report_B.csv").write_text(
        "area_km2,perimeter_km,elev_min,elev_max,elev_mean,slope_mean_deg\n"
        f"{report['geometry']['area_km2']},{report['geometry']['perimeter_km']},"
        f"{elev['min']},{elev['max']},{elev['mean']},{slope['mean']}\n"
    )

if __name__ == "__main__":
    import sys
    # args: jobdir dem_path epsg
    main(sys.argv[1], sys.argv[2], sys.argv[3])
