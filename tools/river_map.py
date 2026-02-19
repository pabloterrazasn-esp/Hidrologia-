from pathlib import Path
import numpy as np
import geopandas as gpd
import rasterio
from shapely.geometry import LineString
import matplotlib.pyplot as plt
import contextily as ctx
import requests

# ESRI/Whitebox D8 codes (muy común):
# 1=E,2=SE,4=S,8=SW,16=W,32=NW,64=N,128=NE
DIR_TO_DRC = {
    (0, 1): 1,
    (1, 1): 2,
    (1, 0): 4,
    (1,-1): 8,
    (0,-1): 16,
    (-1,-1): 32,
    (-1,0): 64,
    (-1,1): 128,
}

NEI = list(DIR_TO_DRC.keys())

def _patch_requests_timeout(timeout=15):
    old_get = requests.get
    def _get(url, *args, **kwargs):
        kwargs.setdefault("timeout", timeout)
        kwargs.setdefault("headers", {"user-agent": "Mozilla/5.0"})
        return old_get(url, *args, **kwargs)
    requests.get = _get

def _pick_outlet_point(jobdir: Path):
    # prefer snap outlet in UTM if exists
    for shp in ["outlet_snap_utm.shp", "outlet_utm.shp", "outlet_wgs84.shp"]:
        p = jobdir / shp
        if p.exists():
            g = gpd.read_file(p)
            if len(g) > 0:
                return g.geometry.iloc[0], g.crs
    raise FileNotFoundError("No encontré outlet_*.shp en el jobdir")

def _trace_mainstem(flow_dir, flow_acc, transform, outlet_xy, max_steps=200000):
    # outlet_xy in same CRS as raster
    col, row = ~transform * outlet_xy
    r = int(round(row))
    c = int(round(col))

    h, w = flow_dir.shape
    def inb(rr, cc):
        return 0 <= rr < h and 0 <= cc < w

    # build list of cell centers along mainstem upstream
    path_rc = [(r, c)]
    steps = 0

    while steps < max_steps:
        steps += 1
        best = None
        best_acc = -1.0

        # find neighbors that flow INTO current cell
        for dr, dc in NEI:
            rr = r + dr
            cc = c + dc
            if not inb(rr, cc):
                continue
            dcode = flow_dir[rr, cc]
            # neighbor at (rr,cc) flows to (rr+dr2, cc+dc2)
            # It flows into current (r,c) if its direction points from neighbor to current:
            # That means offset from neighbor to current is (-dr, -dc)
            need_code = DIR_TO_DRC.get((-dr, -dc))
            if need_code is None:
                continue
            if dcode == need_code:
                acc = float(flow_acc[rr, cc])
                if acc > best_acc:
                    best_acc = acc
                    best = (rr, cc)

        if best is None:
            break

        r, c = best
        path_rc.append((r, c))

        # stop if accumulation becomes tiny (avoid noise)
        if best_acc <= 1:
            break

    # convert to coordinates (cell centers)
    coords = []
    for rr, cc in path_rc:
        x, y = transform * (cc + 0.5, rr + 0.5)
        coords.append((x, y))

    if len(coords) < 2:
        return None
    return LineString(coords)

def run_river_basemap(jobdir, zoom=13, dpi=220, stream_quantile=0.92, satellite=False):
    """
    Outputs:
      - basemap_rivers.png (cuenca + red de ríos + cauce principal)
      - mainstem.geojson (cauce principal)
    """
    jobdir = Path(str(jobdir)).expanduser()

    basin = jobdir / "basin_wgs84.geojson"
    if not basin.exists():
        raise FileNotFoundError(f"No existe {basin}")

    flow_dir_path = jobdir / "flow_dir.tif"
    flow_acc_path = jobdir / "flow_acc.tif"
    if not flow_dir_path.exists() or not flow_acc_path.exists():
        raise FileNotFoundError("Faltan flow_dir.tif o flow_acc.tif en el jobdir")

    # load basin and reproject later to 3857 for tiles
    g_basin = gpd.read_file(basin)

    # read rasters (assumed same CRS/transform)
    with rasterio.open(flow_dir_path) as ds_dir, rasterio.open(flow_acc_path) as ds_acc:
        flow_dir = ds_dir.read(1)
        flow_acc = ds_acc.read(1)
        r_crs = ds_dir.crs
        transform = ds_dir.transform

    # outlet geometry in raster CRS
    outlet_geom, ocrs = _pick_outlet_point(jobdir)
    # reproject outlet to raster CRS if needed
    g_out = gpd.GeoDataFrame(geometry=[outlet_geom], crs=ocrs)
    if r_crs is not None and g_out.crs is not None and str(g_out.crs) != str(r_crs):
        g_out = g_out.to_crs(r_crs)
    outlet_xy = (g_out.geometry.iloc[0].x, g_out.geometry.iloc[0].y)

    # stream mask using quantile threshold (robust to basin size)
    thr = np.nanquantile(flow_acc.astype("float64"), stream_quantile)
    streams_mask = flow_acc >= thr

    # mainstem line (in raster CRS)
    mainstem = _trace_mainstem(flow_dir, flow_acc, transform, outlet_xy)
    g_main = None
    if mainstem is not None and r_crs is not None:
        g_main = gpd.GeoDataFrame({"name": ["mainstem"]}, geometry=[mainstem], crs=r_crs)

    # Prepare for basemap tiles (3857)
    g_basin_3857 = g_basin.to_crs(epsg=3857)
    if g_main is not None:
        g_main_3857 = g_main.to_crs(epsg=3857)
    else:
        g_main_3857 = None

    # Convert streams mask points to a downsampled set of points to draw fast
    # (we draw as points; visually becomes “río azul”)
    rows, cols = np.where(streams_mask)
    # downsample if huge
    if rows.size > 200000:
        idx = np.random.choice(rows.size, 200000, replace=False)
        rows, cols = rows[idx], cols[idx]

    xs = []
    ys = []
    for rr, cc in zip(rows, cols):
        x, y = transform * (cc + 0.5, rr + 0.5)
        xs.append(x)
        ys.append(y)

    # put stream points into 3857
    g_pts = gpd.GeoDataFrame(geometry=gpd.points_from_xy(xs, ys), crs=r_crs)
    g_pts_3857 = g_pts.to_crs(epsg=3857)

    # Basemap download safety
    _patch_requests_timeout(15)

    fig, ax = plt.subplots(figsize=(10, 10))

    # Basin outline
    g_basin_3857.boundary.plot(ax=ax, linewidth=3)

    # Streams (blue)
    g_pts_3857.plot(ax=ax, markersize=1, alpha=0.6)

    # Mainstem thicker
    if g_main_3857 is not None:
        g_main_3857.plot(ax=ax, linewidth=4)

    provider = ctx.providers.Esri.WorldImagery if satellite else ctx.providers.OpenStreetMap.Mapnik

    ctx.add_basemap(
        ax,
        source=provider,
        zoom=zoom,
        attribution=False,
        n_connections=1,
    )

    ax.set_axis_off()
    xmin, ymin, xmax, ymax = g_basin_3857.total_bounds
    ax.set_xlim(xmin, xmax)
    ax.set_ylim(ymin, ymax)

    out_png = jobdir / ("basemap_rivers_sat.png" if satellite else "basemap_rivers.png")
    fig.savefig(out_png, dpi=dpi, bbox_inches="tight", pad_inches=0)
    plt.close(fig)

    # Save mainstem geojson
    if g_main is not None:
        out_geo = jobdir / "mainstem.geojson"
        g_main.to_crs(epsg=4326).to_file(out_geo, driver="GeoJSON")

    return out_png

