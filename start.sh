#!/usr/bin/env bash

# Apply DB migrations before starting any service
python -m alembic upgrade head

# Decide which process to run inside the container.
if [ "${RUN_SCHEDULER:-0}" = "1" ]; then
  python scheduler_worker.py
else
  python main.py
fi
