from app import on_shutdown, on_startup, scheduler
from app.operation.warp import WarpOperation, shutdown_warp_tasks
from config import runtime_settings


@on_startup
def register_warp_job():
    on_shutdown(shutdown_warp_tasks)
    if runtime_settings.role.runs_node:
        scheduler.add_job(
            WarpOperation.reconcile,
            "interval",
            seconds=60,
            coalesce=True,
            max_instances=1,
            id="reconcile_warp_profiles",
            replace_existing=True,
        )
