from unittest.mock import AsyncMock

import pytest
from fastapi import HTTPException

from app.models.host import CreateHost
from app.operation import OperatorType, host as host_operation
from app.operation.host import HostOperation

TAG = "mtproto"


def _inbound(
    *,
    modes: dict[str, bool] | None = None,
    tls_domains: list[str] | None = None,
    native: bool = True,
    web_vhosts: list[dict] | None = None,
) -> dict:
    tls_domains = tls_domains or []
    return {
        "tag": TAG,
        "protocol": "mtproto",
        "modes": {"classic": False, "secure": False, "tls": False} | (modes or {}),
        "tls_domain": tls_domains[0] if tls_domains else "",
        "tls_domains": tls_domains,
        "native": native,
        "web_vhosts": web_vhosts or [],
    }


def _host(
    link_type: str | None = None, *, address: list[str] | None = None, sni: list[str] | None = None
) -> CreateHost:
    transport = {"mtproto_settings": {"link_type": link_type}} if link_type else None
    return CreateHost(
        remark="tg",
        address=address if address is not None else ["edge.example.com"],
        inbound_tag=TAG,
        port=443,
        sni=sni or [],
        priority=1,
        transport_settings=transport,
    )


@pytest.fixture
def use_inbound(monkeypatch):
    def _use(inbound: dict) -> None:
        manager = host_operation.core_manager
        monkeypatch.setattr(manager, "get_inbound_by_tag", AsyncMock(return_value=inbound))
        monkeypatch.setattr(manager, "get_inbounds", AsyncMock(return_value=[inbound["tag"]]))

    return _use


async def _validate(host: CreateHost) -> None:
    await HostOperation(OperatorType.API).validate_mtproto_host(AsyncMock(), host)


async def _refused(host: CreateHost) -> str:
    with pytest.raises(HTTPException) as exc:
        await _validate(host)
    assert exc.value.status_code == 400
    return exc.value.detail


@pytest.mark.asyncio
@pytest.mark.parametrize("mode", ["classic", "secure", "tls"])
async def test_link_type_needs_core_mode(use_inbound, mode):
    use_inbound(_inbound(modes={m: m != mode for m in ("classic", "secure", "tls")}, tls_domains=["a.example"]))
    detail = await _refused(_host(mode))
    assert f'"{mode}"' in detail and "mode" in detail

    use_inbound(_inbound(modes={mode: True}, tls_domains=["a.example"] if mode == "tls" else None))
    await _validate(_host(mode))


@pytest.mark.asyncio
async def test_tls_host_sni_must_be_core_domain(use_inbound):
    use_inbound(_inbound(modes={"tls": True}, tls_domains=["front.example", "Alt.Example"]))
    detail = await _refused(_host("tls", sni=["other.example"]))
    assert "other.example" in detail and "fake TLS domain" in detail

    await _validate(_host("tls", sni=["alt.example"]))
    await _validate(_host("tls", sni=["FRONT.example"]))
    await _validate(_host("tls"))


@pytest.mark.asyncio
@pytest.mark.parametrize("link_type", [None, "auto", "tls", "secure", "classic"])
async def test_native_types_need_native_listener(use_inbound, link_type):
    vhosts = [{"host": "proxy.example.com", "base_path": "/", "secret_mode": "dd"}]
    use_inbound(
        _inbound(
            modes={"classic": True, "secure": True, "tls": True},
            tls_domains=["a.example"],
            native=False,
            web_vhosts=vhosts,
        )
    )
    detail = await _refused(_host(link_type))
    assert "native listener" in detail


@pytest.mark.asyncio
async def test_web_host_address_matching(use_inbound):
    use_inbound(_inbound(modes={"secure": True}))
    detail = await _refused(_host("web", address=["proxy.example.com"]))
    assert "WEB vhost" in detail

    vhosts = [{"host": "proxy.example.com", "base_path": "/tg", "secret_mode": "dd"}]
    use_inbound(_inbound(native=False, web_vhosts=vhosts))
    await _validate(_host("web", address=["Proxy.Example.com"]))

    for address in (["{SERVER_IP}"], ["other.example.com"], ["proxy.example.com", "other.example.com"], []):
        detail = await _refused(_host("web", address=address))
        assert "WEB vhost" in detail


@pytest.mark.asyncio
async def test_save_paths_run_the_check(use_inbound, monkeypatch):
    use_inbound(_inbound(modes={"secure": True}))
    monkeypatch.setattr(host_operation, "get_hosts", AsyncMock(return_value=[]))
    operation = HostOperation(OperatorType.API)
    host = _host("classic")
    admin = AsyncMock()

    for call in (
        operation.create_host(AsyncMock(), host, admin),
        operation.modify_host(AsyncMock(), 1, host, admin),
        operation.modify_hosts(AsyncMock(), [_host("secure"), host], admin),
    ):
        with pytest.raises(HTTPException) as exc:
            await call
        assert exc.value.status_code == 400
        assert '"classic"' in exc.value.detail
