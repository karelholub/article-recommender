#!/bin/bash
set -euo pipefail

echo "Starting production-style stack (gunicorn + postgres + migration job)..."
docker compose -f docker-compose.prod.yml up --build
