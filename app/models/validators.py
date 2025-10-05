import re
from datetime import datetime
from decimal import Decimal
from typing import Optional
from urllib.parse import urlparse

from app.db.models import UserStatusCreate


class NumericValidatorMixin:
    @staticmethod
    def cast_to_int(v):
        """
        Static method to validate and convert numeric values to integers.

        Args:
            v: Input value to be converted

        Returns:
            int or None: Converted integer value

        Raises:
            ValueError: If the input cannot be converted to an integer
        """
        if v is None:  # Allow None values
            return v
        elif isinstance(v, float) or isinstance(v, Decimal):  # Allow float or Decimal to int conversion
            return int(v)
        elif isinstance(v, int):  # Allow integers directly
            return v

        raise ValueError("must be an integer, Decimal or a float, not a string")  # Reject strings

    @staticmethod
    def cast_to_float(v):
        """
        Static method to validate and convert numeric values to floats.

        Args:
            v: Input value to be converted

        Returns:
            float or None: Converted float value

        Raises:
            ValueError: If the input cannot be converted to an float
        """
        if v is None:
            return v
        elif isinstance(v, int) or isinstance(v, Decimal):
            return float(v)
        elif isinstance(v, float):
            return v

        raise ValueError("must be an integer, Decimal or a float, not a string")


class ListValidator:
    @staticmethod
    def nullable_list(list: list | None, name: str) -> list:
        if list and len(list) < 1:
            raise ValueError(f"you must select at least one {name}")
        return list

    @staticmethod
    def not_null_list(list: list, name: str) -> list:
        if not list or len(list) < 1:
            raise ValueError(f"you must select at least one {name}")
        return list

    @staticmethod
    def remove_duplicates_preserve_order(list_: list) -> list:
        """
        Remove duplicates from list while preserving order using dict.fromkeys()
        """
        return list(dict.fromkeys(list_))


class PasswordValidator:
    @staticmethod
    def validate_password(value: str | None, check_username: str | None = None):
        if value is None:
            return value  # Allow None for optional passwords

        errors = []
        # Length check
        if len(value) < 12:
            errors.append("Password must be at least 12 characters long")
        # At least 2 digits
        if len(re.findall(r"\d", value)) < 2:
            errors.append("Password must contain at least 2 digits")
        # At least 2 uppercase letters
        if len(re.findall(r"[A-Z]", value)) < 2:
            errors.append("Password must contain at least 2 uppercase letters")
        # At least 2 lowercase letters
        if len(re.findall(r"[a-z]", value)) < 2:
            errors.append("Password must contain at least 2 lowercase letters")
        # At least 1 special character
        if not re.search(r"[!@#$%^&*()\-_=+\[\]{}|;:,.<>?/~`]", value):
            errors.append("Password must contain at least one special character")
        # Check if password contains the username
        if check_username and check_username.lower() in value.lower():
            errors.append("Password cannot contain the username")

        if errors:
            raise ValueError("; ".join(errors))
        return value


class UserValidator:
    @staticmethod
    def validate_status(status, values):
        on_hold_expire = values.data.get("on_hold_expire_duration") or values.data.get("expire_duration")
        expire = values.data.get("expire")
        if status == UserStatusCreate.on_hold:
            if on_hold_expire == 0 or on_hold_expire is None:
                raise ValueError("User cannot be on hold without a valid on_hold_expire_duration.")
            if expire:
                raise ValueError("User cannot be on hold with specified expire.")
        return status

    @staticmethod
    def validate_username(username: str, len_check: bool = True, accept_null: bool = False):
        if accept_null and not username:
            return username

        if len_check and not (3 <= len(username) <= 128):
            raise ValueError("Username only can be 3 to 128 characters.")

        if not re.match(r"^[a-zA-Z0-9-_@.]+$", username):
            raise ValueError("Username can only contain alphanumeric characters, -, _, @, and .")

        # Additional check to prevent consecutive special characters
        if re.search(r"[-_@.]{2,}", username):
            raise ValueError("Username cannot have consecutive special characters")

        return username

    @staticmethod
    def validator_on_hold_timeout(value):
        if value == 0 or isinstance(value, datetime) or value is None:
            return value
        else:
            raise ValueError("on_hold_timeout can be datetime or 0")


class ProxyValidator:
    @staticmethod
    def validate_proxy_url(value: str | None) -> str | None:
        """
        Validates a proxy URL. Accepts HTTP, HTTPS, SOCKS4, SOCKS5, with or without authentication.
        Examples:
            http://host:port
            https://host:port
            socks5://host:port
            http://user:pass@host:port
            socks5://user:pass@host:port
        """
        if value is None:
            return value
        pattern = (
            r"^(?P<scheme>http|https|socks4|socks5)://"
            r"((?P<user>[^\s:@]+):(?P<pass>[^\s:@]+)@)?"
            r"(?P<host>[a-zA-Z0-9\.-]+)"
            r":(?P<port>\d{1,5})$"
        )
        if not re.match(pattern, value):
            raise ValueError(
                "proxy_url must be a valid proxy address (e.g., http://host:port, socks5://user:pass@host:port)"
            )
        return value


class DiscordValidator:
    @staticmethod
    def validate_webhook(value: str | None):
        if value:
            parsed = urlparse(value)
            # validate scheme and hostname
            if parsed.scheme != "https" or parsed.hostname not in {"discord.com"}:
                raise ValueError("Discord webhook must use https scheme and point to 'discord.com'")
        return value


class URLValidator:
    @staticmethod
    def validate_url(value: Optional[str]) -> Optional[str]:
        """
        Validates a general-purpose URL.
        Examples:
            http://example.com
            https://example.com:8443
        """
        if not value:
            return value

        pattern = (
            r"^(?P<scheme>http|https)://"  # Scheme
            r"(:(?P<port>\d{1,5}))?"  # Optional port
            r"(?P<path>/[^\s?#]*)?"  # Optional path
        )

        if not re.match(pattern, value):
            raise ValueError(f"URL must be a valid address (e.g., https://example.com:8443/path): {value}")

        return value


class StringArrayValidator:
    @staticmethod
    def len_check(array: dict | list | set, max: int) -> set[str] | None:
        if array is None:
            return None

        # Ensure the input is a set for validation
        if isinstance(array, set):
            pass
        elif isinstance(array, dict):
            array = set(array.keys())
        else:
            array = set(array)

        compiled_string = ",".join([str(v) for v in array])
        if len(compiled_string) > max:
            raise ValueError(f"String can't be bigger that {max} charachter")
        return array
