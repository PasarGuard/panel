import pytest
from pydantic import ValidationError

from app.models.user import NextPlanModel, UserModify


def test_next_plan_rejects_negative_values():
    with pytest.raises(ValidationError):
        UserModify(next_plan={"data_limit": -1})
    with pytest.raises(ValidationError):
        UserModify(next_plan={"expire": -1})
    assert UserModify(next_plan={"data_limit": 0, "expire": 0}).next_plan.data_limit == 0
    # Responses reuse NextPlanModel: rows stored before the input check must still load.
    assert NextPlanModel(data_limit=-1).data_limit == -1
