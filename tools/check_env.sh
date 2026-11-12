#!/usr/bin/env bash
# Read-only check of a GPU server (e.g. Kratu) for this project. Changes nothing.
# Usage:  bash tools/check_env.sh 2>&1 | tee env_report.txt
line() { printf '\n=== %s ===\n' "$1"; }

line "Host / OS"
hostname; cat /etc/os-release 2>/dev/null | grep -E '^(NAME|VERSION)='; uname -r

line "GPUs (model, memory, driver)"
if command -v nvidia-smi >/dev/null; then
  nvidia-smi --query-gpu=index,name,memory.total,memory.used,utilization.gpu,driver_version --format=csv
  echo; echo "Processes currently using the GPUs:"; nvidia-smi --query-compute-apps=gpu_uuid,pid,used_memory --format=csv 2>/dev/null
else
  echo "nvidia-smi not found"
fi

line "CPU / RAM / disk"
nproc; free -g | head -2; df -h "$HOME" | tail -1

line "Python"
for p in python3 python3.12 python3.11 python3.10; do command -v $p >/dev/null && echo "$p: $($p --version 2>&1)"; done
command -v conda >/dev/null && echo "conda: $(conda --version)"
command -v module >/dev/null && echo "environment modules available ('module avail' to list)"

line "Job scheduler"
for c in sbatch squeue qsub; do command -v $c >/dev/null && echo "$c found"; done
command -v sinfo >/dev/null && sinfo -o "%P %G %l" 2>/dev/null | head

line "Containers (needed only for NVIDIA AODT)"
command -v docker >/dev/null && { docker --version; docker compose version 2>/dev/null || echo "docker compose v2: not available";
  docker info >/dev/null 2>&1 && echo "docker: usable by ${USER:-$(whoami)}" || echo "docker: installed but ${USER:-$(whoami)} cannot use it (needs docker group)"; } || echo "docker: not installed"
command -v nvidia-ctk >/dev/null && nvidia-ctk --version | head -1 || echo "nvidia-container-toolkit: not found"
command -v apptainer >/dev/null && echo "apptainer: $(apptainer --version)"
command -v singularity >/dev/null && echo "singularity: $(singularity --version)"

line "Internet access (pip, OpenStreetMap, GitHub, NVIDIA NGC)"
for u in https://pypi.org/simple/sionna-rt/ https://overpass-api.de/api/status https://github.com https://nvcr.io/v2/; do
  code=$(curl -s -m 15 -o /dev/null -w '%{http_code}' "$u"); echo "$u -> ${code:-no response}"
done
[ -n "$https_proxy$HTTPS_PROXY" ] && echo "proxy set: ${https_proxy:-$HTTPS_PROXY}"
echo; echo "Done. Send env_report.txt back if you want help reading it."
