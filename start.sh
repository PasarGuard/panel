#!/usr/bin/env bash

ROLE="${NODE_ROLE:-panel}"

if [ "${ROLE}" = "node-worker" ] || [ "${IS_NODE_WORKER:-0}" = 1 ]; then
    exec python node_worker.py
elif [ "${ROLE}" = "scheduler" ] || [ "${RUN_SCHEDULER:-0}" = 1 ]; then
    exec python scheduler_worker.py
else
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] Starting PANEL..."
    python -m alembic upgrade head
    exit_code=$?

    if [ $exit_code -ne 0 ]; then
        echo "[$(date '+%Y-%m-%d %H:%M:%S')] ERROR: Database migrations failed"
        exit 1
    fi

    exec python main.py
fi