#!/usr/bin/env bash

# Apply DB migrations before starting any service
python -m alembic upgrade head

# Decide which process to run inside the container.
ROLE="${NODE_ROLE:-panel}"

if [ "${ROLE}" = "node-worker" ] || [ "${IS_NODE_WORKER:-0}" = "1" ]; then
  python node_worker.py
elif [ "${ROLE}" = "scheduler" ] || [ "${RUN_SCHEDULER:-0}" = "1" ]; then
  python scheduler_worker.py
else
  python main.py
fi
