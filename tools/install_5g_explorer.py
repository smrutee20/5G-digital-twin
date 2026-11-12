"""
Install the "Understand 5G" explorer next to every generated 3D twin viewer and add the button that opens it.

    python tools/install_5g_explorer.py

What it does (safe to run any number of times; it never touches data/ or result tables):
  1. copies tools/understand_5g/ (index.html, app.js, data.js) into every results folder that has a twin_3d.html
  2. adds an "Understand 5G ->" button to those twin_3d.html / twin_3d_fragment.html files, if it is missing
  3. adds the same button to tools/viewer_template.html, so future exports (tools/export_3d.py) include it

The explorer is plain HTML + JavaScript. Open results/<scenario>/understand_5g/index.html directly,
or click the button in the twin viewer.
"""
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "tools" / "understand_5g"
MARK = 'id="learn5g"'

CSS = """.learn5g { display: grid; gap: 2px; text-decoration: none; color: #08111b; background: var(--signal); border-radius: 8px; padding: 9px 12px; font: 700 0.95rem var(--body); }
.learn5g small { font: 500 0.72rem var(--mono); color: #08111bcc; }
.learn5g:hover { filter: brightness(1.08); }
"""
ANCHOR = ('<a class="learn5g" id="learn5g" href="understand_5g/index.html?from=twin">Understand 5G &rarr;'
          '<small>core network, call flows, message decodes</small></a>')
SCRIPT = """<script>
/* Pass the twin's carrier settings to the 5G explorer. */
(function () {
  var a = document.getElementById("learn5g");
  try {
    if (!a || typeof D === "undefined" || !D) return;
    var c = D.carrier, raw = c.bw_mhz * 1000 / (c.prb * 12), scs = [15, 30, 60, 120].reduce(function (b, s) { return Math.abs(s - raw) < Math.abs(b - raw) ? s : b; }, 30);
    a.href = "understand_5g/index.html?" + new URLSearchParams({ from: "twin", f: c.f_ghz, bw: c.bw_mhz, prb: c.prb, scs: scs, title: D.title });
  } catch (e) {}
})();
</script>
"""


def patch_html(text: str) -> str:
    """Add the button (CSS + link + script) to a viewer page or the template. Idempotent."""
    if MARK in text:
        return text
    spec = '<div class="spec" id="spec"></div>'
    if spec not in text or "</style>" not in text:
        raise ValueError("viewer layout not recognised (no spec block or style)")
    text = text.replace("</style>", CSS + "</style>", 1)
    text = text.replace(spec, spec + "\n    " + ANCHOR, 1)
    if "</body>" in text:
        text = text.replace("</body>", SCRIPT + "</body>", 1)
    else:
        text = text.rstrip() + "\n" + SCRIPT
    return text


def install(results_dirs=None, verbose=True):
    if not (SRC / "index.html").exists():
        sys.exit(f"missing {SRC}/index.html")
    if results_dirs is None:
        results_dirs = sorted({p.parent for p in (ROOT / "results").rglob("twin_3d.html")})
    for d in results_dirs:
        dst = d / "understand_5g"
        dst.mkdir(exist_ok=True)
        for f in ("index.html", "app.js", "data.js"):
            shutil.copy2(SRC / f, dst / f)
        for name in ("twin_3d.html", "twin_3d_fragment.html"):
            p = d / name
            if p.exists():
                try:
                    p.write_text(patch_html(p.read_text(encoding="utf-8")), encoding="utf-8")
                except ValueError as e:                 # an older page layout: skip it, keep going
                    print(f"skipped {p}: {e}")
        if verbose:
            print(f"installed explorer + button in {d.relative_to(ROOT) if d.is_relative_to(ROOT) else d}")
    tpl = ROOT / "tools" / "viewer_template.html"
    old = tpl.read_text(encoding="utf-8")
    new = patch_html(old)
    if new != old:
        tpl.write_text(new, encoding="utf-8")
        if verbose:
            print("added button to tools/viewer_template.html")


if __name__ == "__main__":
    install()
    print("Open results/<scenario>/twin_3d.html and click 'Understand 5G', "
          "or open tools/understand_5g/index.html directly.")
