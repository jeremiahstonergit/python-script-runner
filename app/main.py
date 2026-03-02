import os
import json
import sys
import secrets
import tempfile
import subprocess
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from fastapi import FastAPI, UploadFile, File, Form, Depends, HTTPException, status
from fastapi.responses import HTMLResponse
from fastapi.security import HTTPBasic, HTTPBasicCredentials
from starlette.background import BackgroundTask
from starlette.responses import FileResponse, JSONResponse

APP_DIR = Path(__file__).resolve().parent
SCRIPTS_DIR = Path(os.getenv("SCRIPTS_DIR", str((APP_DIR.parent / "scripts").resolve())))

SCRIPT_EXT = ".py"
HIDE_PREFIXES = (".", "_")
META_SCAN_LINES = 60

RUN_TIMEOUT_SEC = int(os.getenv("RUN_TIMEOUT_SEC", "300"))

# Basic Auth через ENV. Если не заданы — auth отключен
BASIC_USER = os.getenv("USER")
BASIC_PASS = os.getenv("PASSWORD")

security = HTTPBasic()
app = FastAPI()


def parse_script_meta(script_path: Path) -> Dict[str, str]:
    """
    Считывает метаданные из первых строк скрипта:
      #TITLE: ...
      #INPUT_HINT: ...
      #OUTPUT_EXT: .xlsx|.csv|.zip|...
    """
    meta: Dict[str, str] = {}
    try:
        with script_path.open("r", encoding="utf-8", errors="replace") as f:
            for _ in range(META_SCAN_LINES):
                line = f.readline()
                if not line:
                    break
                line = line.strip()
                if line.startswith("#TITLE:"):
                    meta["title"] = line.split(":", 1)[1].strip()
                elif line.startswith("#INPUT_HINT:"):
                    meta["input_hint"] = line.split(":", 1)[1].strip()
                elif line.startswith("#OUTPUT_EXT:"):
                    meta["output_ext"] = line.split(":", 1)[1].strip()
    except Exception:
        pass

    # дефолты
    meta.setdefault("title", script_path.name)
    meta.setdefault("input_hint", "Загрузите входной файл и запустите обработку.")
    meta.setdefault("output_ext", ".out")
    if not meta["output_ext"].startswith("."):
        meta["output_ext"] = "." + meta["output_ext"]
    return meta


def list_scripts_with_meta() -> List[Tuple[str, Dict[str, str]]]:
    if not SCRIPTS_DIR.exists():
        return []
    items: List[Tuple[str, Dict[str, str]]] = []
    for p in SCRIPTS_DIR.iterdir():
        if not p.is_file():
            continue
        if p.name.startswith(HIDE_PREFIXES):
            continue
        if p.suffix != SCRIPT_EXT:
            continue
        meta = parse_script_meta(p)
        items.append((p.name, meta))
    items.sort(key=lambda x: x[0])
    return items


def require_basic_auth(credentials: HTTPBasicCredentials = Depends(security)) -> None:
    if not BASIC_USER or not BASIC_PASS:
        return

    ok_user = secrets.compare_digest(credentials.username, BASIC_USER)
    ok_pass = secrets.compare_digest(credentials.password, BASIC_PASS)
    if not (ok_user and ok_pass):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Unauthorized",
            headers={"WWW-Authenticate": "Basic"},
        )


def cleanup_files(*paths: str) -> None:
    for p in paths:
        try:
            os.remove(p)
        except FileNotFoundError:
            pass
        except Exception:
            pass


@app.get("/healthz")
def healthz():
    return JSONResponse({"ok": True})


@app.get("/", response_class=HTMLResponse, dependencies=[Depends(require_basic_auth)])
def index():
    scripts = list_scripts_with_meta()
    if not scripts:
        options = '<option value="">(no scripts found)</option>'
        meta_map: Dict[str, Dict[str, str]] = {}
    else:
        options = "\n".join(
            [
                f'<option value="{name}">{meta.get("title", name)} ({meta.get("output_ext",".out")})</option>'
                for name, meta in scripts
            ]
        )
        meta_map = {name: meta for name, meta in scripts}

    meta_json = json.dumps(meta_map, ensure_ascii=False)

    html = f"""
<!doctype html>
<html lang="ru">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>File processor</title>
  <style>
    body {{ font-family: sans-serif; max-width: 820px; margin: 40px auto; padding: 0 16px; }}
    .row {{ margin: 14px 0; }}
    label {{ display:block; margin-bottom: 6px; }}
    input, select, button {{ font-size: 16px; padding: 8px; width: 100%; box-sizing: border-box; }}
    button {{ cursor: pointer; }}
    .hint {{ color: #444; font-size: 14px; line-height: 1.35; }}
    .muted {{ color: #666; font-size: 13px; }}
    code {{ background: #f4f4f4; padding: 1px 4px; border-radius: 4px; }}
  </style>
</head>
<body>
  <h2>Обработка файла</h2>
  <div class="hint">Загрузите файл, выберите обработчик и нажмите <b>Submit</b>. Результат вернётся как скачивание.</div>

  <form action="/run" method="post" enctype="multipart/form-data">
    <div class="row">
      <label>Файл</label>
      <input type="file" name="file" required />
      <div class="muted">Некоторые скрипты ожидают <code>.zip</code> (см. подсказку ниже).</div>
    </div>

    <div class="row">
      <label>Скрипт</label>
      <select id="scriptSelect" name="script" required onchange="updateHint()">
        {options}
      </select>
      <div id="scriptHint" class="hint" style="margin-top:8px;"></div>
    </div>

    <div class="row">
      <button type="submit">Submit</button>
    </div>
  </form>

  <script>
    const META = {meta_json};

    function updateHint() {{
      const sel = document.getElementById('scriptSelect');
      const name = sel.value;
      const hintEl = document.getElementById('scriptHint');
      if (!name || !META[name]) {{
        hintEl.textContent = '';
        return;
      }}
      const meta = META[name];
      const inputHint = meta.input_hint || '';
      const outExt = meta.output_ext || '';
      hintEl.textContent = inputHint + (outExt ? (" Результат: " + outExt) : "");
    }}

    updateHint();
  </script>
</body>
</html>
"""
    return HTMLResponse(html)


@app.post("/run", dependencies=[Depends(require_basic_auth)])
async def run_script(
    script: str = Form(...),
    file: UploadFile = File(...),
):
    scripts = dict(list_scripts_with_meta())
    if script not in scripts:
        raise HTTPException(status_code=400, detail="Unknown script")

    meta = scripts[script]
    output_ext = meta.get("output_ext", ".out")
    if not output_ext.startswith("."):
        output_ext = "." + output_ext

    script_path = (SCRIPTS_DIR / script).resolve()

    # защита от path traversal
    if script_path.parent != SCRIPTS_DIR.resolve():
        raise HTTPException(status_code=400, detail="Invalid script path")

    # входной временный файл
    in_suffix = Path(file.filename or "").suffix or ".bin"
    with tempfile.NamedTemporaryFile(delete=False, suffix=in_suffix) as in_tmp:
        in_path = in_tmp.name
        await file.seek(0)
        while True:
            chunk = await file.read(1024 * 1024)
            if not chunk:
                break
            in_tmp.write(chunk)

    # выходной временный файл (расширение из метаданных скрипта)
    out_fd, out_path = tempfile.mkstemp(suffix=output_ext)
    os.close(out_fd)

    cmd = [
        sys.executable,
        str(script_path),
        "--input", in_path,
        "--output", out_path,
    ]

    try:
        proc = subprocess.run(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=RUN_TIMEOUT_SEC,
            check=False,
            text=True,
        )
    except subprocess.TimeoutExpired:
        cleanup_files(in_path, out_path)
        raise HTTPException(status_code=504, detail=f"Script timeout after {RUN_TIMEOUT_SEC}s")

    if proc.returncode != 0:
        cleanup_files(in_path, out_path)
        err = (proc.stderr or proc.stdout or "").strip()
        err = err[:4000] if err else "Script failed"
        raise HTTPException(status_code=500, detail=err)

    in_base = Path(file.filename or "input").stem
    script_base = Path(script).stem
    download_name = f"{in_base}__{script_base}{output_ext}"

    return FileResponse(
        out_path,
        media_type="application/octet-stream",
        filename=download_name,
        background=BackgroundTask(cleanup_files, in_path, out_path),
    )
