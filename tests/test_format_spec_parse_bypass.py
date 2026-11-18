import pytest

from app.models.host import validate_format_variables
from app.subscription.share import _format_dynamic_value
from app.utils.helpers import MAX_FORMAT_SPEC_NUMBER, has_oversized_format_spec

OVERSIZED_THEN_UNBALANCED = [
    "{USERNAME:>" + str(MAX_FORMAT_SPEC_NUMBER + 1) + "}{",
    "{USERNAME:>100000000}{",
    "{USERNAME:.300}}}x}",
    "/ws/{USERNAME:0300}{0",
    "{USERNAME}{",
]


class _CountingField:
    def __init__(self):
        self.formatted = 0

    def __format__(self, spec):
        self.formatted += 1
        return "x"


@pytest.mark.parametrize("value", OVERSIZED_THEN_UNBALANCED)
def test_a_value_that_parses_only_up_to_a_stray_brace_is_never_formatted(value):
    field = _CountingField()

    assert _format_dynamic_value(value, {"USERNAME": field}) == value
    assert field.formatted == 0
    assert has_oversized_format_spec(value)
    with pytest.raises(ValueError):
        validate_format_variables(value)


def test_balanced_values_are_still_formatted():
    field = _CountingField()

    assert not has_oversized_format_spec("{USERNAME:>5}{{x}}")
    assert _format_dynamic_value("{USERNAME:>5}{{x}}", {"USERNAME": field}) == "x{x}"
    assert field.formatted == 1
