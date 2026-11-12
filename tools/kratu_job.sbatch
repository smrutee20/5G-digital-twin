#!/bin/bash
# SLURM job for running the study on one GPU. Use only if Kratu runs SLURM (check: `which sbatch`).
# Submit:  mkdir -p logs && sbatch tools/kratu_job.sbatch            (IITGN, config/iitgn.yaml)
#          mkdir -p logs && DT_CONFIG=config/<name>.yaml sbatch tools/kratu_job.sbatch
# Adjust the partition name to what `sinfo` shows on your cluster.
#SBATCH --job-name=5g-dt
#SBATCH --gres=gpu:1
#SBATCH --cpus-per-task=8
#SBATCH --mem=48G
#SBATCH --time=04:00:00
#SBATCH --output=logs/%x-%j.out
##SBATCH --partition=gpu

set -euo pipefail
cd "${SLURM_SUBMIT_DIR:-$(dirname "$0")/..}"
mkdir -p logs
source .venv/bin/activate
export DT_CONFIG="${DT_CONFIG:-config/iitgn.yaml}"
nvidia-smi --query-gpu=name,memory.used,memory.total --format=csv
python -c "import mitsuba as mi; mi.set_variant('cuda_ad_mono_polarized'); print('Mitsuba CUDA backend OK')"
python -u run_all.py
