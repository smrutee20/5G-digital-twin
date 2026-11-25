# The whole twin (3D page + Configure server with Sionna RT on the CPU) in one image.
#   docker build -t 5g-digital-twin .
#   docker run -p 8765:8765 5g-digital-twin          then open http://localhost:8765
# Published for linux/amd64 and linux/arm64 by .github/workflows/docker.yml as ghcr.io/smrutee20/5g-digital-twin.
FROM python:3.12-slim-trixie

# Dr.Jit (under Mitsuba / Sionna RT) compiles the ray tracer with LLVM at run time when there is no NVIDIA GPU.
# It looks for libLLVM itself; DRJIT_LIBLLVM_PATH points it at Debian's, whatever the architecture.
# libatomic1: Dr.Jit's own library needs it on arm64.
RUN apt-get update \
 && apt-get install -y --no-install-recommends libllvm19 libatomic1 \
 && rm -rf /var/lib/apt/lists/* \
 && ln -s "$(ls /usr/lib/*-linux-gnu/libLLVM.so.19* | head -n 1)" /usr/local/lib/libLLVM.so
ENV DRJIT_LIBLLVM_PATH=/usr/local/lib/libLLVM.so \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app
COPY requirements.txt .
RUN pip install -r requirements.txt

# Only what the page and the server need (see .dockerignore for what never enters the build).
COPY config.py run.py viewer.html ./
COPY twin/ twin/
COPY net/ net/
COPY server/ server/
COPY tools/build_site.py tools/
COPY vendor/ vendor/
COPY scenes/ scenes/
COPY data/ data/
# The published page (docs/index.html) carries the twin data, including the v2 walking routes, which are not in
# the repository (data/study_v2/ is git-ignored). twin.html = the current viewer.html + that data, so an image built
# on any machine or in CI shows the same twin as the website, with the local server instead of the static flag.
COPY docs/index.html docs/
RUN python tools/build_site.py --twin-only && rm -r docs \
 && python -c "import mitsuba as mi; mi.set_variant('llvm_ad_mono_polarized'); print('Mitsuba', mi.__version__, mi.variant())"

# Run as a normal user; it owns the coverage-map cache (server/cache/) and Dr.Jit's kernel cache (~/.drjit).
RUN useradd --create-home --uid 1000 twin && mkdir -p server/cache && chown -R twin:twin server/cache
USER twin

ENV TWIN_HOST=0.0.0.0 TWIN_PORT=8765 TWIN_MAX_RAYS=1e6 TWIN_MAX_UES=50
EXPOSE 8765
HEALTHCHECK --interval=30s --timeout=5s --start-period=60s \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8765/health', timeout=4)" || exit 1
CMD ["python", "-m", "server"]
