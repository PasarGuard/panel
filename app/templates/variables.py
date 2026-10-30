"""The variables client templates, custom variables and their validation agree on."""

# Typed like the values `setup_format_variables` builds, so templates are checked against what they will see.
SAMPLE_FORMAT_VARIABLES = {
    "SERVER_IP": "203.0.113.10",
    "SERVER_IPV6": "2001:db8::1",
    "USERNAME": "sample_user",
    "DATA_USAGE": "1.0 GB",
    "DATA_LIMIT": "10.0 GB",
    "DATA_LEFT": "9.0 GB",
    "DAYS_LEFT": 12,
    "EXPIRE_DATE": "2030-01-01",
    "JALALI_EXPIRE_DATE": "1408-10-11",
    "TIME_LEFT": "12d",
    "STATUS_EMOJI": "✅",
    "USAGE_PERCENTAGE": 10.0,
    "ADMIN_USERNAME": "admin",
    "PROFILE_TITLE": "Subscription",
    "PROTOCOL": "vless",
    "TRANSPORT": "tcp",
    "url": "https://sub.example.com/sub/token",
    "format": "xray",
}
# A user without a data limit or expiry gets "∞" in place of numbers.
UNLIMITED_FORMAT_VARIABLES = SAMPLE_FORMAT_VARIABLES | dict.fromkeys(
    ("DATA_LIMIT", "DATA_LEFT", "DAYS_LEFT", "EXPIRE_DATE", "JALALI_EXPIRE_DATE", "TIME_LEFT", "USAGE_PERCENTAGE"), "∞"
)
BUILTIN_FORMAT_VARIABLES = set(SAMPLE_FORMAT_VARIABLES)
# Custom variable keys are upper case, so they cannot shadow `hosts`, the host list that client templates receive.
BUILTIN_CUSTOM_VARIABLE_KEYS = {variable.upper() for variable in BUILTIN_FORMAT_VARIABLES}

# Per request or per host, so they do not exist when a template is rendered once for validation (`hosts` is sampled).
REQUEST_VARIABLES = {"url", "format", "PROFILE_TITLE", "PROTOCOL", "TRANSPORT"}
