from types import SimpleNamespace

import pytest

from app.telegram.handlers import error_handler


@pytest.mark.asyncio
async def test_handle_exception_value_error_message_path(monkeypatch, fake_state, fake_message):
    state = fake_state
    state._data = {"messages_to_delete": [1, 2]}
    msg = type(fake_message)(text="x")
    update = SimpleNamespace(message=msg, callback_query=None, bot=msg.bot)
    event = SimpleNamespace(update=update, exception=ValueError("bad value"))

    await error_handler.handle_exception(event, state)

    msg.answer.assert_awaited_once()


@pytest.mark.asyncio
async def test_handle_exception_validation_error_callback_truncates(monkeypatch, fake_callback):
    callback = type(fake_callback)()
    update = SimpleNamespace(message=None, callback_query=callback, bot=callback.bot)

    class FakeValidationError(Exception):
        pass

    monkeypatch.setattr(error_handler, "ValidationError", FakeValidationError)
    monkeypatch.setattr(error_handler, "format_validation_error", lambda exc: "x" * 250)
    event = SimpleNamespace(update=update, exception=FakeValidationError("boom"))

    await error_handler.handle_exception(event, state=None)

    callback.answer.assert_awaited_once()
    sent_text = callback.answer.await_args.args[0]
    assert len(sent_text) == 200


@pytest.mark.asyncio
async def test_handle_exception_escapes_the_error_in_messages_only(fake_message, fake_callback):
    msg = type(fake_message)(text="x")
    event = SimpleNamespace(
        update=SimpleNamespace(message=msg, callback_query=None, bot=msg.bot),
        exception=ValueError("Group VIP <EU> is disabled"),
    )
    await error_handler.handle_exception(event, state=None)
    assert msg.answer.await_args.args[0] == "❌ Error: Group VIP &lt;EU&gt; is disabled"

    callback = type(fake_callback)()
    event = SimpleNamespace(
        update=SimpleNamespace(message=None, callback_query=callback, bot=callback.bot),
        exception=ValueError("Group VIP <EU> is disabled"),
    )
    await error_handler.handle_exception(event, state=None)
    assert callback.answer.await_args.args[0] == "❌ Error: Group VIP <EU> is disabled"  # alerts are plain text
