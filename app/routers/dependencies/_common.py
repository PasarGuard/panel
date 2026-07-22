from dataclasses import dataclass
from inspect import Parameter, Signature
from typing import Any, Callable, cast

from fastapi import Header, HTTPException, Query, status
from fastapi.params import Header as HeaderParam
from fastapi.params import Query as QueryParam
from pydantic import BaseModel, ValidationError
from pydantic_core import PydanticUndefined


def build_query(model_cls: type[BaseModel], **kwargs: Any) -> BaseModel:
    try:
        return model_cls(**kwargs)
    except ValidationError as exc:
        first_error = exc.errors()[0]
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=first_error["msg"]) from exc


@dataclass(frozen=True)
class ParameterOverride:
    annotation: object
    default: object


def query_param(annotation: object, default: object) -> ParameterOverride:
    return ParameterOverride(annotation=annotation, default=default)


def make_query_dependency(
    cls: type[BaseModel], field_overrides: dict[str, object] | None = None
) -> Callable[..., BaseModel]:
    field_overrides = field_overrides or {}
    parameters: list[Parameter] = []

    for field_name, field_info in cls.model_fields.items():
        annotation = field_info.annotation
        if field_name in field_overrides:
            override = field_overrides[field_name]
            if isinstance(override, ParameterOverride):
                annotation = override.annotation
                default = override.default
            else:
                default = override
        elif field_info.default_factory is not None:
            default = field_info.get_default(call_default_factory=True)
        elif field_info.default is PydanticUndefined:
            default = Parameter.empty
        else:
            default = field_info.default

        # Ensure everything is explicitly a Query parameter to prevent Orval body generation
        if not isinstance(default, (QueryParam, ParameterOverride)) and default is not Parameter.empty:
            default = Query(default)

        parameters.append(
            Parameter(
                field_name,
                Parameter.KEYWORD_ONLY,
                default=default,
                annotation=annotation,
            )
        )

    def factory(**kwargs: Any) -> BaseModel:
        return build_query(cls, **{key: value for key, value in kwargs.items() if value is not None})

    factory_func = cast(Any, factory)
    factory_func.__signature__ = Signature(parameters)
    factory_func.__name__ = f"{cls.__name__}_query_factory"
    return cast(Callable[..., BaseModel], factory_func)


def make_header_dependency(
    cls: type[BaseModel], field_overrides: dict[str, object] | None = None
) -> Callable[..., BaseModel]:
    field_overrides = field_overrides or {}
    parameters: list[Parameter] = []

    for field_name, field_info in cls.model_fields.items():
        annotation = field_info.annotation
        if field_name in field_overrides:
            override = field_overrides[field_name]
            if isinstance(override, ParameterOverride):
                annotation = override.annotation
                default = override.default
            else:
                default = override
        elif field_info.default_factory is not None:
            default = field_info.get_default(call_default_factory=True)
        elif field_info.default is PydanticUndefined:
            default = Parameter.empty
        else:
            default = field_info.default

        # Ensure everything is explicitly a Header parameter
        if not isinstance(default, (HeaderParam, ParameterOverride)):
            alias = field_info.alias if field_info.alias else field_name.replace("_", "-").title()
            if default is Parameter.empty:
                default = Header(..., alias=alias)
            else:
                default = Header(default, alias=alias)

        parameters.append(
            Parameter(
                field_name,
                Parameter.KEYWORD_ONLY,
                default=default,
                annotation=annotation,
            )
        )

    def factory(**kwargs: Any) -> BaseModel:
        return build_query(cls, **{key: value for key, value in kwargs.items() if value is not None})

    factory_func = cast(Any, factory)
    factory_func.__signature__ = Signature(parameters)
    factory_func.__name__ = f"{cls.__name__}_header_factory"
    return cast(Callable[..., BaseModel], factory_func)
