#!/usr/bin/env bash

# Decide which process to run inside the container.
ROLE="${NODE_ROLE:-panel}"

if [ "${ROLE}" = "node-worker" ] || [ "${IS_NODE_WORKER:-0}" = "1" ]; then
  python node_worker.py
elif [ "${ROLE}" = "scheduler" ] || [ "${RUN_SCHEDULER:-0}" = "1" ]; then
  python scheduler_worker.py
else
  # Apply DB migrations before starting any service
  python -m alembic upgrade head
  python main.py
fi
