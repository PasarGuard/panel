import pytest

from app import settings as app_settings


class _NoSettingsDB:
    async def __aenter__(self):
        return object()

    async def __aexit__(self, exc_type, exc, tb):
        return False


@pytest.fixture(autouse=True)
def _empty_settings_table(monkeypatch: pytest.MonkeyPatch):
    async def no_row(db):
        return None

    monkeypatch.setattr(app_settings, "GetDB", _NoSettingsDB)
    monkeypatch.setattr(app_settings, "get_settings", no_row)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "accessor",
    [
        "telegram_settings",
        "webhook_settings",
        "notification_settings",
        "notification_enable",
        "subscription_settings",
        "hwid_settings",
        "general_settings",
        "cleanup_settings",
    ],
)
async def test_every_accessor_reports_the_missing_settings_row_instead_of_an_attribute_error(accessor: str):
    cached_accessor = getattr(app_settings, accessor)
    await cached_accessor.cache.clear()

    try:
        with pytest.raises(RuntimeError) as raised:
            await cached_accessor()
    finally:
        await cached_accessor.cache.clear()

    message = str(raised.value)
    assert "9af04c077ede" in message
    assert "alembic upgrade head" in message
