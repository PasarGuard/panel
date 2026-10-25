"""Client rules on the subscription endpoint run only for a validly signed token."""

from fastapi import status

from app.operation.subscription import SubscriptionOperation
from config import subscription_env_settings
from tests.api import client


def test_invalid_subscription_token_never_reaches_the_client_rules(monkeypatch):
    def must_not_run(*args, **kwargs):
        raise AssertionError("client rules evaluated for an unsigned token")

    monkeypatch.setattr(SubscriptionOperation, "detect_client_rule", staticmethod(must_not_run))

    response = client.get(
        f"/{subscription_env_settings.path}/not-a-valid-token-at-all.bad-signature",
        headers={"user-agent": "a" * 1024 + "!"},
    )
    assert response.status_code == status.HTTP_404_NOT_FOUND, response.text
