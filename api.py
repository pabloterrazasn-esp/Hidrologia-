import os
from pathlib import Path

from fastapi import FastAPI, UploadFile, File
from pydantic import BaseModel
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

app = FastAPI(title="TerraNava")

# (Opcional) servir /static si existe la carpeta
STATIC_DIR = Path(__file__).parent / "static"
if STATIC_DIR.exists():
    app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")

RESULTS_DIR = Path(__file__).parent / "public" / "results"
RESULTS_DIR.mkdir(parents=True, exist_ok=True)
app.mount("/results", StaticFiles(directory=str(RESULTS_DIR)), name="results")

# Carpeta temporal (funciona en Render)
APP_TMP = Path(os.getenv("APP_TMP", "/tmp/terranava"))
APP_TMP.mkdir(parents=True, exist_ok=True)

DEM_FILE = APP_TMP / "dem.tif"


@app.api_route("/", methods=["GET", "HEAD"])
def root():
    return {"status": "TerraNava API running", "dem_exists": DEM_FILE.exists()}


@app.get("/dem-status")
def dem_status():
    return {"exists": DEM_FILE.exists(), "path": str(DEM_FILE)}

@app.post("/upload-dem")
async def upload_dem(file: UploadFile = File(...)):
    name = (file.filename or "").lower()
    if not (name.endswith(".tif") or name.endswith(".tiff")):
        return JSONResponse({"ok": False, "error": "El DEM debe ser .tif/.tiff"}, status_code=400)

    # guardar en /tmp/terranava/dem.tif
    with open(DEM_FILE, "wb") as f:
        while True:
            chunk = await file.read(1024 * 1024)  # 1MB
            if not chunk:
                break
            f.write(chunk)

    size_mb = DEM_FILE.stat().st_size / (1024 * 1024)
    return {"ok": True, "path": str(DEM_FILE), "size_mb": round(size_mb, 2)}



@app.get("/health")
def health():
    return JSONResponse({"ok": True})


class RunRequest(BaseModel):
    lat: float
    lon: float


@app.post("/run")
def run_pipeline(req: RunRequest):
    # 1) verificar DEM en server
    if not DEM_FILE.exists():
        return JSONResponse({"ok": False, "error": "No hay DEM en el servidor. Sube uno en /upload-dem"}, status_code=400)

    # 2) crear carpeta de salida (timestamp simple)
    import time
    run_id = str(int(time.time()))
    out_dir = RESULTS_DIR / run_id
    out_dir.mkdir(parents=True, exist_ok=True)

    # 3) Importar pipeline SOLO aquí (para no tumbar la app al arrancar)
    try:
        from tools.pipeline import run_all  # <- vamos a crear/ajustar esto si aún no existe
    except Exception as e:
        return JSONResponse({"ok": False, "error": "No se pudo importar tools.pipeline.run_all", "detail": str(e)}, status_code=500)

    # 4) ejecutar
    try:
        outputs = run_all(
            dem_path=str(DEM_FILE),
            lat=req.lat,
            lon=req.lon,
            out_dir=str(out_dir),
        )
    except Exception as e:
        return JSONResponse({"ok": False, "error": "Fallo ejecutando pipeline", "detail": str(e)}, status_code=500)

    # 5) devolver links públicos
    # outputs debe devolver rutas dentro de out_dir
    def to_url(path: str):
        name = Path(path).name
        return f"/results/{run_id}/{name}"

    resp = {"ok": True, "run_id": run_id, "files": {}}
    for k, v in (outputs or {}).items():
        try:
            resp["files"][k] = to_url(v)
        except Exception:
            pass

    return resp
