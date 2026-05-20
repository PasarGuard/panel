from fastapi import APIRouter

from . import (
    admin,
    admin_role,
    core,
    client_template,
    group,
    home,
    host,
    node,
    settings,
    setup,
    subscription,
    system,
    user,
    user_template,
    hwid,
)

api_router = APIRouter()

routers = [
    home.router,
    admin.router,
    admin_role.router,
    setup.router,
    system.router,
    settings.router,
    group.router,
    core.router,
    client_template.router,
    host.router,
    node.router,
    user.router,
    subscription.router,
    user_template.router,
    hwid.router,
]

for router in routers:
    api_router.include_router(router)

__all__ = ["api_router"]
