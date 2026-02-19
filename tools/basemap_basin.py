from pathlib import Path
import geopandas as gpd
import matplotlib.pyplot as plt
import contextily as ctx
import requests

def run_basemap_basin_png(jobdir, zoom: int = 13, dpi: int = 220):
    """
    Genera basemap tipo Google + borde de cuenca.
    Ajustes anti-cuelgue:
      - zoom más bajo por defecto (13)
      - dpi moderado
      - requests con timeout global
    """
    # Timeout global para requests (evita colgarse “para siempre”)
    old_get = requests.get
    def _get(url, *args, **kwargs):
        kwargs.setdefault("timeout", 20)   # 20s por tile
        return old_get(url, *args, **kwargs)
    requests.get = _get

    jobdir = Path(str(jobdir)).expanduser()
    basin_geojson = jobdir / "basin_wgs84.geojson"
    if not basin_geojson.exists():
        raise FileNotFoundError(f"No existe {basin_geojson}")

    gdf = gpd.read_file(basin_geojson).to_crs(epsg=3857)

    fig, ax = plt.subplots(figsize=(10, 10))
    gdf.boundary.plot(ax=ax, linewidth=3)

    # Proveedor más “estable” (si quieres imagery, luego volvemos a Esri con zoom bajo)
    ctx.add_basemap(
        ax,
        source=ctx.providers.OpenStreetMap.Mapnik,
        zoom=zoom,
        attribution=False,
    )

    ax.set_axis_off()
    xmin, ymin, xmax, ymax = gdf.total_bounds
    ax.set_xlim(xmin, xmax)
    ax.set_ylim(ymin, ymax)

    out = jobdir / "basemap_basin.png"
    fig.savefig(out, dpi=dpi, bbox_inches="tight", pad_inches=0)
    plt.close(fig)
    return out
