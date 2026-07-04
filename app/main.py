import os
import json
import sys
import tempfile
import subprocess
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from fastapi import FastAPI, UploadFile, File, Form, HTTPException
from fastapi.responses import HTMLResponse
from starlette.background import BackgroundTask
from starlette.responses import FileResponse, JSONResponse

APP_DIR = Path(__file__).resolve().parent
SCRIPTS_DIR = Path(os.getenv("SCRIPTS_DIR", str((APP_DIR.parent / "scripts").resolve())))

SCRIPT_EXT = ".py"
HIDE_PREFIXES = (".", "_")
META_SCAN_LINES = 60

RUN_TIMEOUT_SEC = int(os.getenv("RUN_TIMEOUT_SEC", "300"))

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


@app.get("/", response_class=HTMLResponse)
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
  <title>Обработка файлов</title>
  <style>
    :root {{
      color-scheme: light;
      --bg: #f6f7fb;
      --card: rgba(255, 255, 255, 0.88);
      --card-border: rgba(148, 163, 184, 0.24);
      --text: #111827;
      --muted: #64748b;
      --primary: #4f46e5;
      --primary-dark: #3730a3;
      --primary-soft: #eef2ff;
      --ring: rgba(79, 70, 229, 0.22);
      --shadow: 0 24px 70px rgba(15, 23, 42, 0.14);
      --radius: 28px;
    }}

    * {{ box-sizing: border-box; }}

    body {{
      min-height: 100vh;
      margin: 0;
      font-family: Inter, ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
      color: var(--text);
      background:
        radial-gradient(circle at top left, rgba(99, 102, 241, 0.24), transparent 34rem),
        radial-gradient(circle at bottom right, rgba(14, 165, 233, 0.18), transparent 30rem),
        linear-gradient(135deg, #f8fafc 0%, var(--bg) 48%, #eef2ff 100%);
    }}

    .page {{
      width: min(100%, 1040px);
      margin: 0 auto;
      padding: 56px 20px;
    }}

    .hero {{
      display: grid;
      grid-template-columns: minmax(0, 1fr) 340px;
      gap: 28px;
      align-items: stretch;
    }}

    .intro, .card {{
      border: 1px solid var(--card-border);
      background: var(--card);
      box-shadow: var(--shadow);
      backdrop-filter: blur(18px);
      border-radius: var(--radius);
    }}

    .intro {{
      padding: 42px;
      overflow: hidden;
      position: relative;
    }}

    .intro::after {{
      content: "";
      position: absolute;
      inset: auto -70px -90px auto;
      width: 230px;
      height: 230px;
      border-radius: 999px;
      background: linear-gradient(135deg, rgba(79, 70, 229, 0.22), rgba(14, 165, 233, 0.14));
    }}

    .badge {{
      display: inline-flex;
      align-items: center;
      gap: 8px;
      padding: 8px 12px;
      border-radius: 999px;
      color: var(--primary-dark);
      background: var(--primary-soft);
      font-weight: 700;
      font-size: 14px;
      letter-spacing: 0.01em;
    }}

    h1 {{
      max-width: 720px;
      margin: 22px 0 14px;
      font-size: clamp(36px, 7vw, 68px);
      line-height: 0.95;
      letter-spacing: -0.06em;
    }}

    .lead {{
      max-width: 620px;
      margin: 0;
      color: var(--muted);
      font-size: 18px;
      line-height: 1.65;
    }}

    .steps {{
      display: grid;
      gap: 14px;
      padding: 24px;
      min-height: 100%;
    }}

    .step {{
      display: flex;
      gap: 12px;
      align-items: flex-start;
      padding: 16px;
      border-radius: 20px;
      background: rgba(248, 250, 252, 0.76);
      border: 1px solid rgba(226, 232, 240, 0.9);
    }}

    .step b {{
      display: grid;
      flex: 0 0 32px;
      width: 32px;
      height: 32px;
      place-items: center;
      border-radius: 12px;
      color: white;
      background: linear-gradient(135deg, var(--primary), #06b6d4);
    }}

    .step span {{ color: var(--muted); line-height: 1.45; }}

    form.card {{
      margin-top: 28px;
      padding: 30px;
    }}

    .grid {{
      display: grid;
      grid-template-columns: 1fr 1fr;
      gap: 20px;
    }}

    .field {{ display: grid; gap: 10px; }}

    label {{ font-weight: 800; letter-spacing: -0.01em; }}

    input, select, button {{
      width: 100%;
      font: inherit;
      border: 1px solid #dbe3ef;
      border-radius: 18px;
      transition: border-color 0.2s ease, box-shadow 0.2s ease, transform 0.2s ease;
    }}

    input, select {{
      min-height: 58px;
      padding: 15px 16px;
      background: rgba(255, 255, 255, 0.92);
      color: var(--text);
    }}

    input:focus, select:focus {{
      outline: none;
      border-color: var(--primary);
      box-shadow: 0 0 0 5px var(--ring);
    }}

    input[type="file"] {{ padding: 12px; }}
    input[type="file"]::file-selector-button {{
      margin-right: 14px;
      border: 0;
      border-radius: 14px;
      padding: 10px 14px;
      color: var(--primary-dark);
      background: var(--primary-soft);
      font-weight: 800;
      cursor: pointer;
    }}

    .hint {{
      color: var(--muted);
      font-size: 14px;
      line-height: 1.5;
    }}

    code {{
      padding: 3px 7px;
      border-radius: 9px;
      color: var(--primary-dark);
      background: var(--primary-soft);
      font-weight: 700;
    }}

    .script-hint {{
      margin-top: 20px;
      padding: 18px;
      border-radius: 20px;
      background: #f8fafc;
      border: 1px dashed #cbd5e1;
      min-height: 58px;
    }}

    button {{
      margin-top: 24px;
      min-height: 60px;
      border: 0;
      color: white;
      cursor: pointer;
      font-weight: 900;
      letter-spacing: -0.01em;
      background: linear-gradient(135deg, var(--primary), #0ea5e9);
      box-shadow: 0 18px 36px rgba(79, 70, 229, 0.28);
    }}

    button:hover {{ transform: translateY(-2px); box-shadow: 0 22px 44px rgba(79, 70, 229, 0.34); }}
    button:active {{ transform: translateY(0); }}

    @media (max-width: 820px) {{
      .page {{ padding: 28px 14px; }}
      .hero, .grid {{ grid-template-columns: 1fr; }}
      .intro, form.card {{ padding: 24px; }}
      .steps {{ padding: 20px; }}
    }}
  </style>
</head>
<body>
  <main class="page">
    <section class="hero" aria-labelledby="page-title">
      <div class="intro">
        <div class="badge">⚡ Быстрая обработка файлов</div>
        <h1 id="page-title">Запустите нужный скрипт в пару кликов</h1>
        <p class="lead">Загрузите файл, выберите обработчик и получите готовый результат сразу после выполнения. Интерфейс открыт без лишнего экрана авторизации.</p>
      </div>
      <aside class="card steps" aria-label="Порядок работы">
        <div class="step"><b>1</b><span>Выберите исходный файл с компьютера.</span></div>
        <div class="step"><b>2</b><span>Укажите скрипт обработки и проверьте подсказку.</span></div>
        <div class="step"><b>3</b><span>Нажмите кнопку — результат скачается автоматически.</span></div>
      </aside>
    </section>

    <form class="card" action="/run" method="post" enctype="multipart/form-data">
      <div class="grid">
        <div class="field">
          <label for="fileInput">Файл</label>
          <input id="fileInput" type="file" name="file" required />
          <div class="hint">Некоторые скрипты ожидают <code>.zip</code> — проверьте подсказку выбранного обработчика.</div>
        </div>

        <div class="field">
          <label for="scriptSelect">Скрипт</label>
          <select id="scriptSelect" name="script" required onchange="updateHint()">
            {options}
          </select>
          <div class="hint">Выберите сценарий для входного файла.</div>
        </div>
      </div>

      <div id="scriptHint" class="hint script-hint" aria-live="polite"></div>
      <button type="submit">Запустить обработку →</button>
    </form>
  </main>

  <script>
    const META = {meta_json};

    function updateHint() {{
      const sel = document.getElementById('scriptSelect');
      const name = sel.value;
      const hintEl = document.getElementById('scriptHint');
      if (!name || !META[name]) {{
        hintEl.textContent = 'Выберите скрипт, чтобы увидеть требования к входному файлу и формат результата.';
        return;
      }}
      const meta = META[name];
      const inputHint = meta.input_hint || 'Загрузите входной файл и запустите обработку.';
      const outExt = meta.output_ext || '';
      hintEl.textContent = inputHint + (outExt ? (" Результат: " + outExt) : "");
    }}

    updateHint();
  </script>
</body>
</html>
"""
    return HTMLResponse(html)


@app.post("/run")
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
