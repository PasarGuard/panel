import os
import re
from datetime import UTC, datetime
from io import StringIO
from uuid import UUID

import yaml

from app.utils.helpers import yml_uuid_representer
from app.utils.system import readable_size

_YAML_OPTIONS = {"allow_unicode": True, "indent": 2, "sort_keys": False}

yaml.add_representer(UUID, yml_uuid_representer)

# libyaml's emitter is several times faster than PyYAML's pure-Python one, but it writes some input
# differently: it escapes characters outside the Basic Multilingual Plane (emoji such as flags, common in
# remarks) and puts those strings in double quotes, handles U+0085 and a CR differently, cannot encode lone
# surrogates, writes empty keys and keys of 123 or more characters as simple keys and ends a top-level scalar
# without "...". Astral characters are swapped for private-use characters (written as is by both emitters)
# during the fast dump and swapped back afterwards, and the other inputs above use the pure-Python dumper.
# The output is then byte-identical except for double-quoted strings wider than the 80-column line width,
# which the two emitters fold at different points; both parse to the same value.
_LIBYAML_UNSAFE = re.compile("[\r\x85\ud800-\udfff\ue000-\uf8ff]")
_ASTRAL = re.compile("[\U00010000-\U0010ffff]")
# The pure-Python emitter writes astral characters as is only outside double quotes, so a string holding one
# must not contain anything that forces double quotes (control characters, line breaks, BOM, noncharacters).
_NO_DOUBLE_QUOTES = re.compile("[\x20-\x7e\xa0-\u2027\u202a-\ud7ff\ue000-\ufefe\uff00-\ufffd\U00010000-\U0010fffe]*")
_PLACEHOLDER_START, _PLACEHOLDER_END = 0xE000, 0xF8FF


class _FallbackToPureDumper(Exception):
    pass


_FastDumper = None
if yaml.__with_libyaml__:

    class _FastDumper(yaml.CDumper):
        def __init__(self, *args, **kwargs):
            super().__init__(*args, **kwargs)
            self.placeholders: dict[str, str] = {}

        def represent_str(self, data):
            if _LIBYAML_UNSAFE.search(data):
                raise _FallbackToPureDumper
            if _ASTRAL.search(data):
                if not _NO_DOUBLE_QUOTES.fullmatch(data):
                    raise _FallbackToPureDumper
                data = _ASTRAL.sub(self._placeholder, data)
            return super().represent_str(data)

        def represent_mapping(self, tag, mapping, flow_style=None):
            keys = mapping.keys() if hasattr(mapping, "keys") else (key for key, _ in mapping)
            if any(
                isinstance(key, str)
                and (not key or len(key) >= 123 or len(key.encode("utf-8", "surrogatepass")) >= 128)
                for key in keys
            ):
                raise _FallbackToPureDumper
            return super().represent_mapping(tag, mapping, flow_style)

        def _placeholder(self, match: re.Match) -> str:
            char = match.group()
            placeholder = self.placeholders.get(char)
            if placeholder is None:
                code = _PLACEHOLDER_START + len(self.placeholders)
                if code > _PLACEHOLDER_END:
                    raise _FallbackToPureDumper
                placeholder = self.placeholders[char] = chr(code)
            return placeholder

    _FastDumper.add_representer(str, _FastDumper.represent_str)
    _FastDumper.add_representer(UUID, yml_uuid_representer)


def to_yaml(obj):
    if not obj:
        return ""

    if _FastDumper is not None and isinstance(obj, (dict, list)):
        stream = StringIO()
        dumper = _FastDumper(stream, **_YAML_OPTIONS)
        try:
            dumper.open()
            dumper.represent(obj)
            dumper.close()
        except _FallbackToPureDumper:
            pass
        else:
            return stream.getvalue().translate({ord(p): char for char, p in dumper.placeholders.items()})
        finally:
            dumper.dispose()

    return yaml.dump(obj, **_YAML_OPTIONS)


def exclude_keys(obj, *target_keys):
    return {key: val for key, val in obj.items() if key not in target_keys}


def only_keys(obj, *target_keys):
    return {key: val for key, val in obj.items() if key in target_keys}


def datetimeformat(dt):
    if isinstance(dt, int):
        dt = datetime.fromtimestamp(dt, tz=UTC)
    formatted_datetime = dt.strftime("%Y-%m-%d %H:%M:%S")
    return formatted_datetime


def env_override(value, key):
    return os.getenv(key, value)


CUSTOM_FILTERS = {
    "yaml": to_yaml,
    "except": exclude_keys,
    "only": only_keys,
    "datetime": datetimeformat,
    "bytesformat": readable_size,
}
