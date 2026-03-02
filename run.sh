#!/bin/bash
set -euo pipefail

if [ -f ".venv/bin/activate" ]; then
  source .venv/bin/activate
fi

echo "Ensuring local data files exist..."
python bootstrap_data.py

echo "Starting Flask server on http://localhost:5001"
python app.py
