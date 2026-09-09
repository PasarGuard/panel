from pydantic import BaseModel, Field, field_validator


class ReorderRequest(BaseModel):
    ordered_ids: list[int] = Field(min_length=2, max_length=10000)

    @field_validator("ordered_ids")
    @classmethod
    def validate_unique_ids(cls, value: list[int]) -> list[int]:
        """Reject duplicate IDs before the reorder operation accesses the database."""
        if len(value) != len(set(value)):
            raise ValueError("ordered_ids must not contain duplicates")
        return value
