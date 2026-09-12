from types import SimpleNamespace

from app.db.crud.wireguard import wg_core_tags, wg_interface_configs, wg_namespaces


def wg_core(interface_name="wg0", address=("10.0.0.1/24",)):
    return SimpleNamespace(
        id=1,
        config={
            "interface_name": interface_name,
            "private_key": "irrelevant-for-namespaces",
            "listen_port": 51820,
            "address": list(address),
        },
    )


def xray_core_with_wg(tag="2907_wireguard", address=("10.30.0.1/24",)):
    """Xray core serving WireGuard through a wireguard inbound."""
    return SimpleNamespace(
        id=2,
        config={
            "inbounds": [
                {
                    "tag": "vless-tcp",
                    "protocol": "vless",
                    "port": 443,
                    "settings": {"clients": [], "decryption": "none"},
                },
                {
                    "tag": tag,
                    "protocol": "wireguard",
                    "port": 1443,
                    "settings": {
                        "secretKey": "kJ9mS7yQ0bV3nX1cZ5aR8tW2uY4iO6pL0dF7gH9jK1s=",
                        "address": list(address),
                        "mtu": 1420,
                    },
                },
            ],
            "outbounds": [{"protocol": "freedom"}],
        },
    )


class TestWgInterfaceConfigs:
    def test_native_wg_core_is_passed_through(self):
        configs = wg_interface_configs([wg_core()])
        assert configs == [wg_core().config]

    def test_wireguard_inbound_of_xray_core_is_picked_up(self):
        """WireGuard served by Xray must participate in peer provisioning.

        Before this, only cores of type wg were considered, so users in a
        group pointing at an Xray wireguard inbound never got keys or peer
        IPs and their subscription came out empty.
        """
        configs = wg_interface_configs([xray_core_with_wg()])
        assert configs == [{"interface_name": "2907_wireguard", "address": ["10.30.0.1/24"]}]

    def test_non_wireguard_inbounds_are_ignored(self):
        core = xray_core_with_wg()
        core.config["inbounds"] = [i for i in core.config["inbounds"] if i["protocol"] != "wireguard"]
        assert wg_interface_configs([core]) == []

    def test_inbound_without_tag_is_skipped(self):
        core = xray_core_with_wg()
        core.config["inbounds"][1]["tag"] = "   "
        assert wg_interface_configs([core]) == []

    def test_inbound_without_address_still_yields_tag(self):
        """A subnet-less interface has no pool, but its tag must stay visible
        so user_has_wireguard_access still grants key generation."""
        core = xray_core_with_wg(address=())
        configs = wg_interface_configs([core])
        assert configs == [{"interface_name": "2907_wireguard", "address": []}]

    def test_malformed_inbound_entries_do_not_crash(self):
        core = xray_core_with_wg()
        core.config["inbounds"].append("not-a-dict")
        core.config["inbounds"].append({"protocol": "wireguard"})
        configs = wg_interface_configs([core])
        assert configs == [{"interface_name": "2907_wireguard", "address": ["10.30.0.1/24"]}]

    def test_both_core_kinds_together(self):
        configs = wg_interface_configs([wg_core(), xray_core_with_wg()])
        assert len(configs) == 2
        assert {c["interface_name"] for c in configs} == {"wg0", "2907_wireguard"}


class TestWgCoreTags:
    def test_tag_of_xray_wireguard_inbound_is_reported(self):
        assert wg_core_tags([xray_core_with_wg()]) == {"2907_wireguard"}

    def test_tags_from_mixed_cores(self):
        assert wg_core_tags([wg_core(), xray_core_with_wg()]) == {"wg0", "2907_wireguard"}

    def test_no_wireguard_anywhere(self):
        core = xray_core_with_wg()
        core.config["inbounds"] = [i for i in core.config["inbounds"] if i["protocol"] != "wireguard"]
        assert wg_core_tags([core]) == set()


class TestWgNamespaces:
    def test_namespace_built_from_xray_wireguard_inbound(self):
        namespaces = wg_namespaces([xray_core_with_wg()])
        assert list(namespaces) == ["10.30.0.0/24"]
        ns = namespaces["10.30.0.0/24"]
        assert ns.tags == frozenset({"2907_wireguard"})
        # .1 is the interface address itself and must not be handed to a peer
        assert (int(ns.subnet.network_address) + 1) - int(ns.subnet.network_address) in ns.reserved

    def test_namespaces_from_both_core_kinds(self):
        namespaces = wg_namespaces([wg_core(), xray_core_with_wg()])
        assert set(namespaces) == {"10.0.0.0/24", "10.30.0.0/24"}
