#!/bin/sh
set -eu

echo "Bootstrapping local data files..."
python bootstrap_data.py

if [ "${RECOMMENDER_DB_BACKEND:-sqlite}" = "postgres" ] && [ "${RUN_MIGRATIONS:-true}" = "true" ]; then
  echo "Running PostgreSQL migrations..."
  python scripts/migrate_postgres.py
fi

if [ "$#" -gt 0 ]; then
  echo "Starting custom command: $*"
  exec "$@"
fi

echo "Starting Flask app on 0.0.0.0:5001"
exec python app.py
