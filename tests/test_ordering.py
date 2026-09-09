import pytest
from pydantic import ValidationError

from app.models.ordering import ReorderRequest


def test_reorder_request_allows_largest_supported_collection() -> None:
    ordered_ids = list(range(1, 10001))

    request = ReorderRequest(ordered_ids=ordered_ids)

    assert request.ordered_ids == ordered_ids


def test_reorder_request_rejects_unbounded_collection() -> None:
    with pytest.raises(ValidationError):
        ReorderRequest(ordered_ids=list(range(1, 10002)))
