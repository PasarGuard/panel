from app.nats.rpc_client import NatsRpcClient
from app.nats.rpc_service import BaseRpcService
from app.utils.logger import get_logger
from config import ROLE, NATS_SCHEDULER_RPC_SUBJECT, NATS_SCHEDULER_RPC_TIMEOUT

logger = get_logger("scheduler-nats")


scheduler_nats_client = NatsRpcClient(
    NATS_SCHEDULER_RPC_SUBJECT,
    NATS_SCHEDULER_RPC_TIMEOUT,
    error_message="Scheduler RPC error",
)
_scheduler_rpc_service = BaseRpcService(
    subject=NATS_SCHEDULER_RPC_SUBJECT,
    logger=logger,
    role_check=lambda: ROLE.runs_scheduler,
    start_msg="Scheduler RPC service started",
    stop_msg="Scheduler RPC service stopped",
)


async def start_scheduler_rpc():
    await _scheduler_rpc_service.start()


async def stop_scheduler_rpc():
    await _scheduler_rpc_service.stop()
