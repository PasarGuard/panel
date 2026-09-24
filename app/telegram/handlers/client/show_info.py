from io import BytesIO
from urllib.parse import urlparse

from aiogram import F, Router
from aiogram.types import BufferedInputFile, Message
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.settings import ConfigFormat
from app.operation import OperatorType
from app.operation.subscription import SubscriptionOperation
from app.operation.user import UserOperation
from app.telegram.utils.qr import send_subscription_qr
from app.telegram.utils.texts import Message as Texts

user_operations = UserOperation(OperatorType.TELEGRAM)
subscription_operations = SubscriptionOperation(OperatorType.TELEGRAM)

router = Router(name="show_info")


def _subscription_token(text: str) -> str:
    text = text.strip()
    if text.startswith("/start "):
        text = text.split(maxsplit=1)[1].strip()

    parsed = urlparse(text)
    if parsed.scheme and parsed.netloc:
        parts = [part for part in parsed.path.split("/") if part]
        if "sub" in parts:
            sub_index = parts.index("sub")
            if len(parts) > sub_index + 1:
                return parts[sub_index + 1]
        if parts:
            return parts[-1]

    return text.strip("/").split("/")[-1]


@router.message(F.text)
async def get_user(event: Message, db: AsyncSession):
    """get exact user, otherwise not found"""
    token = _subscription_token(event.text)
    try:
        db_user = await user_operations.get_validated_sub(db, token)
        user = await user_operations.validate_user(db_user)
    except ValueError:
        return await event.reply(Texts.user_not_found)

    await event.reply(Texts.client_user_details(user))
    await send_subscription_qr(event, user.subscription_url, user.username)

    try:
        user_with_inbounds = await subscription_operations.validated_user(db_user)
        configs = (await subscription_operations.fetch_config(user_with_inbounds, ConfigFormat.links))[0]
    except ValueError:
        return

    if configs:
        if len(configs) < 4085:  # Telegram message limit (including formatting)
            await event.answer(f"<pre>{configs}</pre>")
        else:
            file = BytesIO(configs.encode("utf-8"))
            await event.answer_document(
                BufferedInputFile(file.read(), f"{user.username}.txt"),
            )
