"""FastAPI dependency accessors."""

from __future__ import annotations

from typing import Annotated, cast

from fastapi import Cookie, Depends, Request

from backend.config import Settings
from backend.domain.ports import AssignmentService


def get_settings(request: Request) -> Settings:
    return cast(Settings, request.app.state.settings)


def get_assignment_service(request: Request) -> AssignmentService:
    return cast(AssignmentService, request.app.state.assignment_service)


def get_owner_cookie(
    request: Request,
    owner_cookie: Annotated[str | None, Cookie(alias="claros_owner")] = None,
) -> str | None:
    settings = get_settings(request)
    if settings.owner_cookie_name == "claros_owner":
        return owner_cookie
    return request.cookies.get(settings.owner_cookie_name)


SettingsDependency = Annotated[Settings, Depends(get_settings)]
ServiceDependency = Annotated[AssignmentService, Depends(get_assignment_service)]
OwnerCookieDependency = Annotated[str | None, Depends(get_owner_cookie)]
