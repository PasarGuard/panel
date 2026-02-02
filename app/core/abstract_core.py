from abc import ABC, abstractmethod


class AbstractCore(ABC):
    @abstractmethod
    def __init__(self, config: dict, exclude_inbound_tags: list[str], fallbacks_inbound_tags: list[str]) -> None:
        raise NotImplementedError

    @abstractmethod
    def to_str(self, **json_kwargs) -> str:
        raise NotImplementedError

    @property
    @abstractmethod
    def inbounds_by_tag(self) -> dict:
        raise NotImplementedError

    @abstractmethod
    def to_json(self) -> dict:
        """Convert the core config to a JSON-serializable dictionary."""
        raise NotImplementedError

    @classmethod
    @abstractmethod
    def from_json(cls, data: dict) -> "AbstractCore":
        """Reconstruct the core config from a dictionary."""
        raise NotImplementedError

    @property
    @abstractmethod
    def inbounds(self) -> list[str]:
        raise NotImplementedError
