"""Transport handlers run in worker threads on hosts shared through the host cache, so they must not modify them."""

from app.models.subscription import WebSocketTransportConfig
from app.subscription.xray import XrayConfiguration


def test_random_user_agent_does_not_modify_the_host_it_was_built_from():
    config = WebSocketTransportConfig(http_headers={"X-A": "1"}, random_user_agent=True)
    xray = XrayConfiguration(user_agent_template_content='{"list": ["ua"]}')

    ws = xray._transport_ws(config, "/")
    upgrade = xray._transport_httpupgrade(config, "/")

    assert "User-Agent" in ws["headers"]
    assert "User-Agent" in upgrade["headers"]
    assert config.http_headers == {"X-A": "1"}
