import os
from pathlib import Path

from fastapi import FastAPI, UploadFile, File
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

app = FastAPI(title="TerraNava")

# (Opcional) servir /static si existe la carpeta
STATIC_DIR = Path(__file__).parent / "static"
if STATIC_DIR.exists():
    app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")

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
