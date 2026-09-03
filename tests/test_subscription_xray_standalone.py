import json

from app.subscription.xray import XrayConfiguration


def test_standalone_xray_profile_is_appended_without_proxy_injection():
    configuration = XrayConfiguration()
    template = json.dumps(
        {
            "remarks": "Serverless {USERNAME}",
            "inbounds": [{"tag": "socks", "protocol": "socks", "port": 10808, "settings": {}}],
            "outbounds": [{"tag": "DIRECT", "protocol": "freedom", "settings": {"fragment": {}}}],
            "routing": {"rules": []},
        }
    )

    configuration.add_standalone(template, {"USERNAME": "alice"})
    rendered = json.loads(configuration.render())

    assert len(rendered) == 1
    assert rendered[0]["remarks"] == "Serverless alice"
    assert rendered[0]["outbounds"] == [{"tag": "DIRECT", "protocol": "freedom", "settings": {"fragment": {}}}]


def test_standalone_xray_profile_formats_nested_template_variables():
    configuration = XrayConfiguration()
    template = json.dumps(
        {
            "remarks": "{PROFILE_NAME}",
            "inbounds": [{"tag": "socks", "protocol": "socks", "port": 10808, "settings": {}}],
            "outbounds": [{"tag": "DIRECT", "protocol": "freedom", "settings": {}}],
            "routing": {"rules": [{"domain": ["full:{USERNAME}.example.com"], "outboundTag": "DIRECT"}]},
        }
    )

    configuration.add_standalone(template, {"PROFILE_NAME": "Local bypass", "USERNAME": "alice"})

    assert configuration.config[0]["routing"]["rules"][0]["domain"] == ["full:alice.example.com"]
