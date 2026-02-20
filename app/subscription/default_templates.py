DEFAULT_CLASH_SUBSCRIPTION_TEMPLATE = """mode: rule
mixed-port: 7890
ipv6: true

tun:
  enable: true
  stack: mixed
  dns-hijack:
    - "any:53"
  auto-route: true
  auto-detect-interface: true
  strict-route: true

dns:
  enable: true
  listen: :1053
  ipv6: true
  nameserver:
    - 'https://1.1.1.1/dns-query#PROXY'
  proxy-server-nameserver:
    - '178.22.122.100'
    - '78.157.42.100'

sniffer:
  enable: true
  override-destination: true
  sniff:
    HTTP:
      ports: [80, 8080-8880]
    TLS:
      ports: [443, 8443]
    QUIC:
      ports: [443, 8443]

{{ conf | except("proxy-groups", "port", "mode", "rules") | yaml }}

proxy-groups:
- name: 'PROXY'
  type: 'select'
  proxies:
  - 'Fastest'
  {{ proxy_remarks | yaml | indent(2) }}

- name: 'Fastest'
  type: 'url-test'
  proxies:
  {{ proxy_remarks | yaml | indent(2) }}

rules:
  - MATCH,PROXY
"""

DEFAULT_XRAY_SUBSCRIPTION_TEMPLATE = """{
  "log": {
    "access": "",
    "error": "",
    "loglevel": "warning"
  },
  "inbounds": [
    {
      "tag": "socks",
      "port": 10808,
      "listen": "0.0.0.0",
      "protocol": "socks",
      "sniffing": {
        "enabled": true,
        "destOverride": [
          "http",
          "tls"
        ],
        "routeOnly": false
      },
      "settings": {
        "auth": "noauth",
        "udp": true,
        "allowTransparent": false
      }
    },
    {
      "tag": "http",
      "port": 10809,
      "listen": "0.0.0.0",
      "protocol": "http",
      "sniffing": {
        "enabled": true,
        "destOverride": [
          "http",
          "tls"
        ],
        "routeOnly": false
      },
      "settings": {
        "auth": "noauth",
        "udp": true,
        "allowTransparent": false
      }
    }
  ],
  "outbounds": [],
  "dns": {
    "servers": [
      "1.1.1.1",
      "8.8.8.8"
    ]
  },
  "routing": {
    "domainStrategy": "AsIs",
    "rules": []
  }
}
"""

DEFAULT_SINGBOX_SUBSCRIPTION_TEMPLATE = """{
  "log": {
    "level": "warn",
    "timestamp": false
  },
  "dns": {
    "servers": [
      {
        "tag": "dns-remote",
        "address": "1.1.1.2",
        "detour": "proxy"
      },
      {
        "tag": "dns-local",
        "address": "local",
        "detour": "direct"
      }
    ],
    "rules": [
      {
        "outbound": "any",
        "server": "dns-local"
      }
    ],
    "final": "dns-remote"
  },
  "inbounds": [
    {
      "type": "tun",
      "tag": "tun-in",
      "interface_name": "sing-tun",
      "address": [
        "172.19.0.1/30",
        "fdfe:dcba:9876::1/126"
      ],
      "auto_route": true,
      "route_exclude_address": [
        "192.168.0.0/16",
        "10.0.0.0/8",
        "169.254.0.0/16",
        "172.16.0.0/12",
        "fe80::/10",
        "fc00::/7"
      ]
    }
  ],
  "outbounds": [
    {
      "type": "selector",
      "tag": "proxy",
      "outbounds": null,
      "interrupt_exist_connections": true
    },
    {
      "type": "urltest",
      "tag": "Best Latency",
      "outbounds": null
    },
    {
      "type": "direct",
      "tag": "direct"
    }
  ],
  "route": {
    "rules": [
      {
        "inbound": "tun-in",
        "action": "sniff"
      },
      {
        "protocol": "dns",
        "action": "hijack-dns"
      }
    ],
    "final": "proxy",
    "auto_detect_interface": true,
    "override_android_vpn": true
  },
  "experimental": {
    "cache_file": {
      "enabled": true,
      "store_rdrc": true
    }
  }
}
"""

DEFAULT_USER_AGENT_TEMPLATE = """{
  "list": [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Linux; Android 10; K) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Mobile Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:126.0) Gecko/20100101 Firefox/126.0",
    "Mozilla/5.0 (iPhone; CPU iPhone OS 17_4_1 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.4.1 Mobile/15E148 Safari/604.1"
  ]
}
"""

DEFAULT_GRPC_USER_AGENT_TEMPLATE = """{
  "list": [
    "grpc-dotnet/2.41.0 (.NET 6.0.1; CLR 6.0.1; net6.0; windows; x64)",
    "grpc-python-asyncio/1.62.1 grpc-c/39.0.0 (linux; chttp2)",
    "grpc-go/1.58.1",
    "grpc-java-okhttp/1.55.1",
    "grpc-ruby/1.62.0 grpc-c/39.0.0 (osx; chttp2)"
  ]
}
"""

DEFAULT_TEMPLATE_CONTENTS_BY_LEGACY_KEY = {
    "CLASH_SUBSCRIPTION_TEMPLATE": DEFAULT_CLASH_SUBSCRIPTION_TEMPLATE,
    "XRAY_SUBSCRIPTION_TEMPLATE": DEFAULT_XRAY_SUBSCRIPTION_TEMPLATE,
    "SINGBOX_SUBSCRIPTION_TEMPLATE": DEFAULT_SINGBOX_SUBSCRIPTION_TEMPLATE,
    "USER_AGENT_TEMPLATE": DEFAULT_USER_AGENT_TEMPLATE,
    "GRPC_USER_AGENT_TEMPLATE": DEFAULT_GRPC_USER_AGENT_TEMPLATE,
}
