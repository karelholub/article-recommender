#!/bin/bash
set -euo pipefail

echo "Starting Article Recommender with PostgreSQL via Docker Compose..."
docker compose up --build
