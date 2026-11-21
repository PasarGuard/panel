from aiogram import F, Router
from aiogram.exceptions import TelegramBadRequest
from aiogram.types import CallbackQuery
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.admin import AdminDetails
from app.models.node import NodeListQuery
from app.operation import OperatorType
from app.operation.node import NodeOperation
from app.operation.system import SystemOperation
from app.settings import telegram_settings
from app.telegram.keyboards.admin import AdminPanel, AdminPanelAction
from app.telegram.utils.filters import HasPermission, IsAdminFilter
from app.telegram.utils.texts import Message as Texts
from app.utils.logger import get_logger

system_operator = SystemOperation(OperatorType.TELEGRAM)
node_operator = NodeOperation(OperatorType.TELEGRAM)
logger = get_logger("telegram-bot")

router = Router(name="main_menu")


async def _render_main_menu(event: CallbackQuery, db: AsyncSession, admin: AdminDetails):
    """Render the main admin panel with permission-aware keyboard."""
    stats = await system_operator.get_system_stats(db, admin)
    settings = await telegram_settings()
    return AdminPanel(
        admin=admin,
        panel_url=settings.mini_app_web_url if settings.mini_app_login else None,
    ).as_markup(), Texts.start(stats, admin.data_limit)


@router.callback_query(IsAdminFilter(), AdminPanel.Callback.filter(AdminPanelAction.refresh == F.action))
async def reload_data(event: CallbackQuery, db: AsyncSession, admin: AdminDetails):
    markup, text = await _render_main_menu(event, db, admin)
    try:
        await event.message.edit_text(text=text, reply_markup=markup)
    except TelegramBadRequest:
        pass
    await event.answer(Texts.refreshed)


@router.callback_query(
    HasPermission("nodes", "reconnect"),
    AdminPanel.Callback.filter(AdminPanelAction.sync_users == F.action),
)
async def sync_users(event: CallbackQuery, db: AsyncSession, admin: AdminDetails):
    await event.answer(Texts.syncing)
    # Disabled and limited nodes have nothing to sync and would only be reported as failures.
    nodes_response = await node_operator.get_db_nodes(db, NodeListQuery(enabled=True))
    failed = []
    for node in nodes_response.nodes:
        try:
            await node_operator.sync_node_users(db, node.id, flush_users=True)
        except ValueError:
            # One node's failure must not leave the others unsynced.
            failed.append(node.name)
        except Exception:
            logger.exception("User sync of node %s failed", node.id)
            failed.append(node.name)
            # A failed query leaves the shared session unusable for the next node and the menu.
            await db.rollback()
    markup, text = await _render_main_menu(event, db, admin)
    try:
        await event.message.edit_text(text=text, reply_markup=markup)
    except TelegramBadRequest:
        pass
    if failed:
        # The callback was answered above and may have expired by now, so this goes out as a message.
        await event.message.answer(Texts.sync_failed(failed))
        return
    try:
        await event.answer(Texts.synced)
    except TelegramBadRequest:
        pass


@router.callback_query(
    HasPermission("nodes", "reconnect"),
    AdminPanel.Callback.filter(AdminPanelAction.reconnect_all_nodes == F.action),
)
async def reconnect_all_nodes(event: CallbackQuery, db: AsyncSession, admin: AdminDetails):
    await event.answer(Texts.reconnecting_nodes)
    await node_operator.restart_all_node(db=db, admin=admin)
    markup, text = await _render_main_menu(event, db, admin)
    try:
        await event.message.edit_text(text=text, reply_markup=markup)
    except TelegramBadRequest:
        pass
    await event.answer(Texts.nodes_reconnected)
