"""
Build the GitHub Pages site (static only, no server):  .venv/bin/python tools/build_site.py

  1. runs run.py, which writes twin.html (the twin data and three.js are already inside it)
  2. copies it to docs/index.html with STATIC_SITE = true: the page then looks for a server only at
     http://localhost:8765/health (the Docker image on the visitor's computer). If one answers, Configure and other
     handover rules use it; if not, Configure shows the "docker run ..." box and other handover rules say so
  3. checks the copy loads nothing from outside the file (no 127.0.0.1, no file paths, no <script src>/<link href>;
     http://localhost:8765 is the one allowed address)

Page-only changes (viewer.html edited, same data):  python tools/build_site.py --reuse-data
  Skips run.py: takes the twin data that is already inside docs/index.html and puts it into the current viewer.html.
  Use it on a machine without the study data (data/study_v2/ is not in the repository, and without it run.py would
  fall back to the v1 routes). It also writes twin.html, so the result can be opened and checked locally.

Docker image (Dockerfile):  python tools/build_site.py --twin-only
  Only twin.html, as --reuse-data, for the image's server; docs/index.html is not touched.

docs/screenshots/ is left as it is. GitHub Pages: Settings -> Pages -> branch main, folder /docs.
"""
import json
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC, OUT = ROOT / "twin.html", ROOT / "docs" / "index.html"
MARK = "const DATA = "
LOCAL_SERVER = '"http://localhost:8765"'                       # viewer.html's LOCAL_SERVER (the Docker image)


def reuse_data():
    """twin.html from the current viewer.html and the data inside docs/index.html (what run.py's build_page does,
    with the saved data instead of a new simulation)."""
    sys.path.insert(0, str(ROOT))
    import config as C
    old = OUT.read_text(encoding="utf-8")
    start = old.index(MARK) + len(MARK)
    data, _ = json.JSONDecoder().raw_decode(old[start:])           # "<\/" in the page is plain "</" once decoded
    data.setdefault("delay_ms", C.DELAY_MS)                         # as run.py adds them (for the live packet status)
    data.setdefault("processing_ms", C.PROCESSING_MS)
    libs = "".join("<script>\n" + (ROOT / "vendor" / f).read_text(encoding="utf-8").replace("</script", "<\\/script")
                   + "\n</script>\n" for f in ("three.min.js", "OrbitControls.js"))
    page = (ROOT / "viewer.html").read_text(encoding="utf-8")
    page = page.replace("<!--LIBRARIES-->", libs).replace("/*DATA*/null", json.dumps(data).replace("</", "<\\/"))
    SRC.write_text(page, encoding="utf-8", newline="\n")
    walk = data["twin"].get("walk_scene", "v1")
    print(f"wrote twin.html from viewer.html and the data in docs/index.html ({len(data['twin']['routes'])} routes, twin {walk})")


def main():
    if "--twin-only" in sys.argv:
        reuse_data()
        return
    if "--reuse-data" in sys.argv:
        reuse_data()
    else:
        subprocess.run([sys.executable, "run.py"], cwd=ROOT, check=True)
    page = SRC.read_text(encoding="utf-8")

    flag = "const STATIC_SITE = false;"
    assert page.count(flag) == 1, "viewer.html: STATIC_SITE flag not found"
    page = page.replace(flag, "const STATIC_SITE = true;")
    page = page.replace('"http://127.0.0.1:8765"', "null")          # the (unused) local-server address

    assert page.count(LOCAL_SERVER) == 1, "viewer.html: LOCAL_SERVER not found"
    checked = page.replace(LOCAL_SERVER, "")                        # the one allowed address (see step 2)
    problems = [p for p in ("127.0.0.1", "localhost:", "file://", "/Users/") if p in checked]
    problems += re.findall(r'<script[^>]+src=|<link[^>]+href="(?!data:)|<img[^>]+src="(?!data:)', checked)
    if problems:
        sys.exit(f"docs/index.html would load outside resources: {sorted(set(problems))}")

    OUT.parent.mkdir(exist_ok=True)
    OUT.write_text(page, encoding="utf-8", newline="\n")
    print(f"wrote {OUT.relative_to(ROOT)} ({OUT.stat().st_size / 1e6:.1f} MB), static (no server calls)")


if __name__ == "__main__":
    main()
