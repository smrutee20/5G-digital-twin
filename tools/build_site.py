"""
Build the GitHub Pages site (static only, no server):  .venv/bin/python tools/build_site.py

  1. runs run.py, which writes twin.html (the twin data and three.js are already inside it)
  2. copies it to docs/index.html with STATIC_SITE = true: the page then never calls the local server, so the
     Configure tab shows "Configure needs the local server (see README)" and other handover rules say so
  3. checks the copy loads nothing from outside the file (no 127.0.0.1, no file paths, no <script src>/<link href>)

docs/screenshots/ is left as it is. GitHub Pages: Settings -> Pages -> branch main, folder /docs.
"""
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC, OUT = ROOT / "twin.html", ROOT / "docs" / "index.html"


def main():
    subprocess.run([sys.executable, "run.py"], cwd=ROOT, check=True)
    page = SRC.read_text(encoding="utf-8")

    flag = "const STATIC_SITE = false;"
    assert page.count(flag) == 1, "viewer.html: STATIC_SITE flag not found"
    page = page.replace(flag, "const STATIC_SITE = true;")
    page = page.replace('"http://127.0.0.1:8765"', "null")          # the (unused) local-server address

    problems = [p for p in ("127.0.0.1", "localhost:", "file://", "/Users/") if p in page]
    problems += re.findall(r'<script[^>]+src=|<link[^>]+href="(?!data:)|<img[^>]+src="(?!data:)', page)
    if problems:
        sys.exit(f"docs/index.html would load outside resources: {sorted(set(problems))}")

    OUT.parent.mkdir(exist_ok=True)
    OUT.write_text(page, encoding="utf-8")
    print(f"wrote {OUT.relative_to(ROOT)} ({OUT.stat().st_size / 1e6:.1f} MB), static (no server calls)")


if __name__ == "__main__":
    main()
