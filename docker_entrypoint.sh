#!/bin/bash
set -e

export DATA_DIR=/data
mkdir -p "$DATA_DIR"

exec uvicorn backend.main:app --host 0.0.0.0 --port 80
