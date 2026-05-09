from fastapi import HTTPException, status
from pydantic import ValidationError


def build_query(model_cls, **kwargs):
    try:
        return model_cls(**kwargs)
    except ValidationError as exc:
        first_error = exc.errors()[0]
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=first_error["msg"]) from exc
