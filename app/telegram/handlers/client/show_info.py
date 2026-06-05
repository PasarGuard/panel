from io import BytesIO
import struct
import zlib

import qrcode
from aiogram import F, Router
from aiogram.types import BufferedInputFile
from aiogram.types import Message
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.settings import ConfigFormat
from app.operation import OperatorType
from app.operation.subscription import SubscriptionOperation
from app.operation.user import UserOperation
from app.telegram.utils.texts import Message as Texts

user_operations = UserOperation(OperatorType.TELEGRAM)
subscription_operations = SubscriptionOperation(OperatorType.TELEGRAM)

router = Router(name="show_info")


def _png_chunk(chunk_type: bytes, data: bytes) -> bytes:
    return (
        struct.pack(">I", len(data)) + chunk_type + data + struct.pack(">I", zlib.crc32(chunk_type + data) & 0xFFFFFFFF)
    )


def _matrix_to_png(matrix: list[list[bool]], scale: int = 8) -> bytes:
    width = len(matrix[0]) * scale
    height = len(matrix) * scale
    rows: list[bytes] = []

    for module_row in matrix:
        pixel_row = b"".join((b"\x00" if module else b"\xff") * scale for module in module_row)
        rows.extend(b"\x00" + pixel_row for _ in range(scale))

    header = struct.pack(">IIBBBBB", width, height, 8, 0, 0, 0, 0)
    return (
        b"\x89PNG\r\n\x1a\n"
        + _png_chunk(b"IHDR", header)
        + _png_chunk(b"IDAT", zlib.compress(b"".join(rows)))
        + _png_chunk(b"IEND", b"")
    )


def _subscription_qr_file(subscription_url: str, username: str) -> BufferedInputFile:
    qr = qrcode.QRCode(error_correction=qrcode.constants.ERROR_CORRECT_M, border=4)
    qr.add_data(subscription_url)
    qr.make(fit=True)
    return BufferedInputFile(_matrix_to_png(qr.get_matrix()), f"{username}-subscription-qr.png")


@router.message(F.text)
async def get_user(event: Message, db: AsyncSession):
    """get exact user, otherwise not found"""
    token = event.text.strip("/").split("/")[-1]
    try:
        db_user = await user_operations.get_validated_sub(db, token)
        user = await user_operations.validate_user(db_user)
        user_with_inbounds = await subscription_operations.validated_user(db_user)
        configs = (await subscription_operations.fetch_config(user_with_inbounds, ConfigFormat.links))[0]
    except ValueError:
        return await event.reply(Texts.user_not_found)

    await event.answer_photo(_subscription_qr_file(user.subscription_url, user.username))

    if configs:
        if len(configs) < 4085:  # Telegram message limit (including formatting)
            await event.reply(Texts.client_user_details(user))
            await event.answer(f"<pre>{configs}</pre>")
        else:
            file = BytesIO(configs.encode("utf-8"))
            await event.answer_document(
                BufferedInputFile(file.read(), f"{user.username}.txt"), caption=Texts.client_user_details(user)
            )
    else:
        await event.reply(Texts.client_user_details(user))
