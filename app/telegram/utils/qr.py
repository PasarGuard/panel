from __future__ import annotations

import struct
import zlib

import qrcode
from aiogram.exceptions import TelegramAPIError
from aiogram.types import BufferedInputFile
from aiogram.types import Message


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


def subscription_qr_file(subscription_url: str, username: str) -> BufferedInputFile:
    qr = qrcode.QRCode(error_correction=qrcode.constants.ERROR_CORRECT_M, border=4)
    qr.add_data(subscription_url)
    qr.make(fit=True)
    return BufferedInputFile(_matrix_to_png(qr.get_matrix()), f"{username}-subscription-qr.png")


async def send_subscription_qr(message: Message, subscription_url: str, username: str) -> None:
    qr_file = subscription_qr_file(subscription_url, username)
    try:
        await message.answer_photo(qr_file)
    except TelegramAPIError:
        await message.answer_document(subscription_qr_file(subscription_url, username))
