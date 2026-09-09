from app.models.ordering import ReorderRequest


def test_reorder_request_allows_large_collections() -> None:
    ordered_ids = list(range(1, 1002))

    request = ReorderRequest(ordered_ids=ordered_ids)

    assert request.ordered_ids == ordered_ids
