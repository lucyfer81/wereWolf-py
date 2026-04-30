#!/bin/bash
cd "$(dirname "$0")"
source .venv/bin/activate
uvicorn src.main:app --reload --port 5004 --host 0.0.0.0
