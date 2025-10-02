from fastapi import APIRouter

from . import admin, core, group, home, host, node, settings, subscription, system, user, user_template

api_router = APIRouter()

# Routers that don't need versioning (home, subscription)
non_versioned_routers = [
    home.router,
    subscription.router,
]

# Routers that need both versioned and non-versioned paths
versioned_routers = [
    admin.router,
    system.router,
    settings.router,
    group.router,
    core.router,
    host.router,
    node.router,
    user.router,
    user_template.router,
]

# Include non-versioned routers
for router in non_versioned_routers:
    api_router.include_router(router)

# Include versioned routers with /api/v1 prefix
v1_router = APIRouter(prefix="/api/v1")
for router in versioned_routers:
    v1_router.include_router(router)
api_router.include_router(v1_router)

# Include the same routers without version prefix for backward compatibility
non_version_router = APIRouter(prefix="/api")
for router in versioned_routers:
    non_version_router.include_router(router)
api_router.include_router(non_version_router)

__all__ = ["api_router"]
