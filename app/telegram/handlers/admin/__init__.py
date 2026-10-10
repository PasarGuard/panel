from aiogram import Router

from app.telegram.utils.filters import IsAdminFilter

from . import bulk_actions, confirm_action, main_menu, user

router = Router(name="admin")

router.message.filter(IsAdminFilter())
router.callback_query.filter(IsAdminFilter())
router.inline_query.filter(IsAdminFilter())

router.include_router(main_menu.router)
router.include_router(confirm_action.router)
router.include_router(bulk_actions.router)

router.include_router(user.router)  # keep this as last one
