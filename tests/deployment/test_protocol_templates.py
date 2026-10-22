import importlib.util
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location("generate_xray_config", ROOT / "scripts/generate_xray_config.py")
generator = importlib.util.module_from_spec(spec)
spec.loader.exec_module(generator)


class ProtocolTemplateTests(unittest.TestCase):
    def test_all_protocols_with_distinct_tags_ports_paths(self):
        config = generator.build_config(behind_tls_proxy=True)
        inbounds = config["inbounds"]
        self.assertEqual([i["protocol"] for i in inbounds], ["vless", "vmess", "trojan"])
        self.assertEqual(len({i["tag"] for i in inbounds}), 3)
        self.assertEqual(len({i["port"] for i in inbounds}), 3)
        self.assertEqual(len({i["streamSettings"]["wsSettings"]["path"] for i in inbounds}), 3)
        self.assertTrue(all(i["settings"]["clients"] == [] for i in inbounds))
        self.assertEqual(inbounds[0]["settings"]["decryption"], "none")

    def test_public_listener_requires_tls(self):
        with self.assertRaises(ValueError):
            generator.build_config(listen="0.0.0.0", behind_tls_proxy=True)
        with self.assertRaises(ValueError):
            generator.build_config()

    def test_certificate_mode(self):
        config = generator.build_config(listen="0.0.0.0", cert="/cert/fullchain.pem", key="/cert/key.pem")
        for inbound in config["inbounds"]:
            tls = inbound["streamSettings"]
            self.assertEqual(tls["security"], "tls")
            self.assertEqual(tls["tlsSettings"]["minVersion"], "1.2")

    def test_invalid_inputs(self):
        for kwargs in (
            {"base_port": 65534},
            {"base_port": 0},
            {"protocols": []},
            {"protocols": ["vless", "vless"]},
            {"protocols": ["unknown"]},
            {"cert": "/cert.pem"},
        ):
            with self.subTest(kwargs=kwargs), self.assertRaises(ValueError):
                generator.build_config(behind_tls_proxy=True, **kwargs)

    def test_certificate_paths_must_be_absolute(self):
        with self.assertRaises(ValueError):
            generator.build_config(cert="cert.pem", key="key.pem")

    def test_subset_and_ipv6_loopback(self):
        config = generator.build_config(protocols=["trojan"], base_port=65535, listen="::1", behind_tls_proxy=True)
        self.assertEqual(config["inbounds"][0]["port"], 65535)
        self.assertEqual(config["inbounds"][0]["listen"], "::1")
