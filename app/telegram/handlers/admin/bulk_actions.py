from datetime import datetime as dt, timezone as tz, timedelta as td

from aiogram import Router, F
from aiogram.exceptions import TelegramBadRequest
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.admin import AdminDetails
from app.models.user import BulkUser, BulkUsersFromTemplate, UsernameGenerationStrategy
from app.models.validators import UserValidator
from app.operation import OperatorType
from app.operation.user import UserOperation
from app.operation.user_template import UserTemplateOperation
from app.telegram.keyboards.admin import AdminPanel, AdminPanelAction
from app.telegram.keyboards.base import CancelKeyboard
from app.telegram.keyboards.bulk_actions import (
    BulkActionPanel,
    BulkAction,
    BulkTemplateSelector,
    UsernameStrategySelector,
)
from app.telegram.keyboards.confim_action import ConfirmAction
from app.telegram.utils import forms
from app.telegram.utils.shared import add_to_messages_to_delete, delete_messages
from app.telegram.utils.texts import Message as Texts

user_operations = UserOperation(OperatorType.TELEGRAM)
user_templates = UserTemplateOperation(OperatorType.TELEGRAM)

router = Router(name="bulk_actions")


def _message_target(event: Message | CallbackQuery) -> Message:
    return event.message if isinstance(event, CallbackQuery) else event


def _chunk_subscription_urls(urls: list[str], limit: int = 3800) -> list[str]:
    """Split subscription urls into chunks that fit Telegram limits."""
    chunks: list[str] = []
    current: list[str] = []
    length = 0

    for url in urls:
        url_length = len(url) + (1 if current else 0)
        if length + url_length > limit:
            chunks.append("\n".join(current))
            current = [url]
            length = len(url)
        else:
            current.append(url)
            length += url_length

    if current:
        chunks.append("\n".join(current))

    return chunks


@router.callback_query(AdminPanel.Callback.filter(AdminPanelAction.bulk_actions == F.action))
async def bulk_actions(event: CallbackQuery):
    await event.message.edit_text(Texts.choose_action, reply_markup=BulkActionPanel().as_markup())


@router.callback_query(BulkActionPanel.Callback.filter(BulkAction.create_from_template == F.action))
async def bulk_create_from_template(event: CallbackQuery, db: AsyncSession, state: FSMContext):
    templates = await user_templates.get_user_templates(db)
    if not templates:
        return await event.answer(Texts.there_is_no_template)

    await delete_messages(event, state, message_ids=[event.message.message_id])
    await state.clear()
    await event.message.answer(Texts.choose_a_template, reply_markup=BulkTemplateSelector(templates).as_markup())


@router.callback_query(BulkTemplateSelector.Callback.filter())
async def bulk_template_chosen(event: CallbackQuery, state: FSMContext, callback_data: BulkTemplateSelector.Callback):
    await delete_messages(event, state, message_ids=[event.message.message_id])
    await state.set_state(forms.BulkCreateFromTemplate.count)
    await state.update_data(template_id=callback_data.template_id, messages_to_delete=[])
    msg = await event.message.answer(Texts.enter_bulk_count, reply_markup=CancelKeyboard().as_markup())
    await add_to_messages_to_delete(state, msg)


@router.message(forms.BulkCreateFromTemplate.count)
async def bulk_template_count(event: Message, state: FSMContext):
    await delete_messages(event, state)
    await add_to_messages_to_delete(state, event)

    try:
        count = int(event.text)
    except (TypeError, ValueError):
        msg = await event.reply(text=Texts.bulk_count_not_valid, reply_markup=CancelKeyboard().as_markup())
        await add_to_messages_to_delete(state, msg)
        return

    if count <= 0 or count > 500:
        msg = await event.reply(text=Texts.bulk_count_not_valid, reply_markup=CancelKeyboard().as_markup())
        await add_to_messages_to_delete(state, msg)
        return

    await state.update_data(count=count, messages_to_delete=[])
    await state.set_state(forms.BulkCreateFromTemplate.strategy)
    msg = await event.answer(Texts.choose_username_strategy, reply_markup=UsernameStrategySelector().as_markup())
    await add_to_messages_to_delete(state, msg)


@router.callback_query(UsernameStrategySelector.Callback.filter())
async def bulk_template_strategy(
    event: CallbackQuery,
    db: AsyncSession,
    state: FSMContext,
    admin: AdminDetails,
    callback_data: UsernameStrategySelector.Callback,
):
    await delete_messages(event, state, message_ids=[event.message.message_id])
    data = await state.get_data()
    template_id = data.get("template_id")
    count = data.get("count")

    if not template_id or not count:
        await state.clear()
        return await event.answer(Texts.canceled)

    strategy = callback_data.strategy
    if strategy == UsernameGenerationStrategy.random:
        return await _perform_bulk_creation(
            event, db, admin, state, template_id=template_id, count=count, strategy=strategy, base_username=None
        )

    await state.update_data(strategy=strategy.value)
    await state.set_state(forms.BulkCreateFromTemplate.username)
    msg = await event.message.answer(Texts.enter_bulk_sequence_username, reply_markup=CancelKeyboard().as_markup())
    await state.update_data(messages_to_delete=[msg.message_id])


@router.message(forms.BulkCreateFromTemplate.username)
async def bulk_template_sequence_username(event: Message, db: AsyncSession, state: FSMContext, admin: AdminDetails):
    await delete_messages(event, state)
    await add_to_messages_to_delete(state, event)

    base_username = (event.text or "").strip()
    try:
        UserValidator.validate_username(base_username)
    except ValueError as e:
        msg = await event.reply(f"❌ {e}", reply_markup=CancelKeyboard().as_markup())
        await add_to_messages_to_delete(state, msg)
        return

    data = await state.get_data()
    template_id = data.get("template_id")
    count = data.get("count")

    if not template_id or not count:
        await state.clear()
        return await event.reply(Texts.canceled)

    await state.update_data(base_username=base_username)
    await state.set_state(forms.BulkCreateFromTemplate.start_number)
    msg = await event.reply(Texts.enter_bulk_sequence_start_number, reply_markup=CancelKeyboard().as_markup())
    await add_to_messages_to_delete(state, msg)


@router.message(forms.BulkCreateFromTemplate.start_number)
async def bulk_template_start_number(event: Message, db: AsyncSession, state: FSMContext, admin: AdminDetails):
    await delete_messages(event, state)
    await add_to_messages_to_delete(state, event)

    text_value = (event.text or "").strip()
    start_number: int | None
    if text_value == "":
        start_number = None
    else:
        try:
            start_number = int(text_value)
        except ValueError:
            msg = await event.reply(text=Texts.start_number_not_valid, reply_markup=CancelKeyboard().as_markup())
            await add_to_messages_to_delete(state, msg)
            return
        if start_number < 0:
            msg = await event.reply(text=Texts.start_number_not_valid, reply_markup=CancelKeyboard().as_markup())
            await add_to_messages_to_delete(state, msg)
            return

    data = await state.get_data()
    template_id = data.get("template_id")
    count = data.get("count")
    base_username = data.get("base_username")

    if not template_id or not count or not base_username:
        await state.clear()
        return await event.reply(Texts.canceled)

    await _perform_bulk_creation(
        event,
        db,
        admin,
        state,
        template_id=template_id,
        count=count,
        strategy=UsernameGenerationStrategy.sequence,
        base_username=base_username,
        start_number=start_number,
    )


async def _perform_bulk_creation(
    event: Message | CallbackQuery,
    db: AsyncSession,
    admin: AdminDetails,
    state: FSMContext,
    template_id: int,
    count: int,
    strategy: UsernameGenerationStrategy,
    base_username: str | None = None,
    start_number: int | None = None,
):
    await delete_messages(event, state)
    target = _message_target(event)

    try:
        payload = BulkUsersFromTemplate(
            count=count,
            strategy=strategy,
            username=base_username,
            user_template_id=template_id,
            start_number=start_number,
        )
        result = await user_operations.bulk_create_users_from_template(db, payload, admin)
    except Exception as e:
        await state.clear()
        return await target.answer(f"❌ {e}")
    await state.clear()

    if result.created == 0:
        return await target.answer(Texts.bulk_users_not_created())

    await target.answer(Texts.bulk_users_created(result.created))
    if result.subscription_urls:
        for chunk in _chunk_subscription_urls(result.subscription_urls):
            await target.answer(chunk)


@router.callback_query(BulkActionPanel.Callback.filter((BulkAction.delete_expired == F.action) & ~F.amount))
async def delete_expired(event: CallbackQuery, state: FSMContext):
    try:
        await event.message.delete()
    except TelegramBadRequest:
        pass
    await state.set_state(forms.DeleteExpired.expired_before)
    msg = await event.message.answer(Texts.enter_expire_before, reply_markup=CancelKeyboard().as_markup())
    await state.update_data(messages_to_delete=[msg.message_id])


@router.message(forms.DeleteExpired.expired_before)
async def process_expire_before(event: Message, state: FSMContext):
    await delete_messages(event, state)
    await add_to_messages_to_delete(state, event)

    if not event.text or not event.text.isnumeric():
        msg = await event.reply(text=Texts.duration_not_valid, reply_markup=CancelKeyboard().as_markup())
        await add_to_messages_to_delete(state, msg)
        return

    await delete_messages(event, state)
    await state.clear()

    await event.answer(
        Texts.confirm_delete_expired(event.text),
        reply_markup=ConfirmAction(
            confirm_action=BulkActionPanel.Callback(action=BulkAction.delete_expired, amount=event.text).pack(),
            cancel_action=AdminPanel.Callback(
                action=AdminPanelAction.bulk_actions,
            ).pack(),
        ).as_markup(),
    )


@router.callback_query(BulkActionPanel.Callback.filter((BulkAction.delete_expired == F.action) & F.amount))
async def delete_expired_done(
    event: CallbackQuery, db: AsyncSession, admin: AdminDetails, callback_data: BulkActionPanel.Callback
):
    expire_before = dt.now(tz.utc) - td(days=int(callback_data.amount))
    result = await user_operations.delete_expired_users(
        db,
        admin,
        expired_before=expire_before,
        expired_after=dt.fromtimestamp(0, tz.utc),
    )
    await event.answer(Texts.users_deleted(result.count))
    await event.message.edit_text(Texts.choose_action, reply_markup=BulkActionPanel().as_markup())


@router.callback_query(BulkActionPanel.Callback.filter((BulkAction.modify_expiry == F.action) & ~F.amount))
async def modify_expiry(event: CallbackQuery, state: FSMContext):
    try:
        await event.message.delete()
    except TelegramBadRequest:
        pass
    await state.set_state(forms.BulkModify.expiry)
    msg = await event.message.answer(Texts.enter_bulk_expiry, reply_markup=CancelKeyboard().as_markup())
    await state.update_data(messages_to_delete=[msg.message_id])


@router.message(forms.BulkModify.expiry)
async def process_expiry(event: Message, state: FSMContext):
    await delete_messages(event, state)
    await add_to_messages_to_delete(state, event)

    try:
        amount = int(event.text)
    except ValueError:
        msg = await event.reply(text=Texts.duration_not_valid, reply_markup=CancelKeyboard().as_markup())
        await add_to_messages_to_delete(state, msg)
        return

    await delete_messages(event, state)
    await state.clear()

    await event.answer(
        Texts.confirm_modify_expiry(amount),
        reply_markup=ConfirmAction(
            confirm_action=BulkActionPanel.Callback(action=BulkAction.modify_expiry, amount=str(amount)).pack(),
            cancel_action=AdminPanel.Callback(
                action=AdminPanelAction.bulk_actions,
            ).pack(),
        ).as_markup(),
    )


@router.callback_query(BulkActionPanel.Callback.filter((BulkAction.modify_expiry == F.action) & F.amount))
async def modify_expiry_done(event: CallbackQuery, db: AsyncSession, callback_data: BulkActionPanel.Callback):
    result = await user_operations.bulk_modify_expire(db, BulkUser(amount=int(callback_data.amount) * 86400))
    await event.answer(Texts.users_expiry_changed(result, int(callback_data.amount)))
    await event.message.edit_text(Texts.choose_action, reply_markup=BulkActionPanel().as_markup())


@router.callback_query(BulkActionPanel.Callback.filter((BulkAction.modify_data_limit == F.action) & ~F.amount))
async def modify_data_limit(event: CallbackQuery, state: FSMContext):
    try:
        await event.message.delete()
    except TelegramBadRequest:
        pass
    await state.set_state(forms.BulkModify.data_limit)
    msg = await event.message.answer(Texts.enter_bulk_data_limit, reply_markup=CancelKeyboard().as_markup())
    await state.update_data(messages_to_delete=[msg.message_id])


@router.message(forms.BulkModify.data_limit)
async def process_data_limit(event: Message, state: FSMContext):
    await delete_messages(event, state)
    await add_to_messages_to_delete(state, event)

    try:
        amount = int(event.text)
    except ValueError:
        msg = await event.reply(text=Texts.data_limit_not_valid, reply_markup=CancelKeyboard().as_markup())
        await add_to_messages_to_delete(state, msg)
        return

    await delete_messages(event, state)
    await state.clear()

    await event.answer(
        Texts.confirm_modify_data_limit(amount),
        reply_markup=ConfirmAction(
            confirm_action=BulkActionPanel.Callback(action=BulkAction.modify_data_limit, amount=str(amount)).pack(),
            cancel_action=AdminPanel.Callback(
                action=AdminPanelAction.bulk_actions,
            ).pack(),
        ).as_markup(),
    )


@router.callback_query(BulkActionPanel.Callback.filter((BulkAction.modify_data_limit == F.action) & F.amount))
async def modify_data_limit_done(event: CallbackQuery, db: AsyncSession, callback_data: BulkActionPanel.Callback):
    result = await user_operations.bulk_modify_datalimit(db, BulkUser(amount=int(callback_data.amount) * (1024**3)))
    await event.answer(Texts.users_data_limit_changed(result, int(callback_data.amount)))
    await event.message.edit_text(Texts.choose_action, reply_markup=BulkActionPanel().as_markup())
