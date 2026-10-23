from unittest.mock import AsyncMock

import pytest

from app.core import hosts as hosts_module
from app.core.xray import XRayConfig
from app.models.host import BaseHost


@pytest.mark.parametrize("download_state", ["disabled", "missing", "invalid"])
async def test_host_snapshot_preserves_download_host_validation(monkeypatch, download_state):
    inbounds = XRayConfig(
        {
            "inbounds": [
                {
                    "tag": tag,
                    "port": port,
                    "protocol": "vless",
                    "settings": {"clients": [], "decryption": "none"},
                    "streamSettings": {"network": "xhttp", "xhttpSettings": {"path": "/" + tag}},
                }
                for tag, port in (("up", 443), ("down", 8443))
            ],
            "outbounds": [{"tag": "direct", "protocol": "freedom"}],
        }
    ).inbounds_by_tag
    inbounds["up"]["download_settings"] = {"address": "stale.example.com"}
    parent = BaseHost(
        id=1,
        remark="parent",
        address={"parent.example.com"},
        inbound_tag="up",
        priority=0,
        transport_settings={"xhttp_settings": {"download_settings": 2}},
    )
    downstream = BaseHost(
        id=2, remark="download", address={"download.example.com"}, inbound_tag="down", priority=0, is_disabled=True
    )
    if download_state == "invalid":
        downstream = downstream.model_copy(update={"port": "invalid"})
    elif download_state == "missing":
        downstream = None
    monkeypatch.setattr(hosts_module, "get_host_by_id", AsyncMock(return_value=downstream))
    global_lookup = AsyncMock(side_effect=AssertionError("Use the committed inbound snapshot"))
    monkeypatch.setattr(hosts_module.core_manager, "get_inbound_by_tag", global_lookup)

    entry = await hosts_module.HostManager()._prepare_host_entry(object(), parent, list(inbounds), inbounds)

    assert entry is not None
    assert entry[0] == parent.id
    download = entry[1].transport_config.download_settings
    if download_state == "disabled":
        assert download.address == ["download.example.com"]
        assert download.port == [8443]
    else:
        assert download is None
    global_lookup.assert_not_awaited()
