from sqlalchemy.exc import IntegrityError

from app.db import AsyncSession
from app.db.crud.client_profile import (
    count_users_by_client_profile,
    create_client_profile,
    get_client_profiles,
    get_client_profiles_simple,
    get_existing_user_ids,
    modify_client_profile,
    remove_client_profiles,
    set_users_client_profile,
)
from app.db.crud.client_template import get_client_template_by_id
from app.db.models import ClientProfile
from app.models.admin import AdminDetails
from app.models.client_profile import (
    BulkClientProfileSelection,
    ClientProfileAssignUsers,
    ClientProfileCreate,
    ClientProfileListQuery,
    ClientProfileModify,
    ClientProfileResponse,
    ClientProfileResponseList,
    ClientProfileSimple,
    ClientProfileSimpleListQuery,
    ClientProfilesSimpleResponse,
    ClientProfileTemplateType,
    ClientProfileUnassignUsers,
    ClientProfileUsersResponse,
    RemoveClientProfilesResponse,
)
from app.nats.message import MessageTopic
from app.nats.router import router
from app.operation.permissions import PermissionDenied, enforce_permission, get_scope_admin_id
from app.subscription.client_profiles import refresh_client_profiles_cache
from app.utils.logger import get_logger

from . import BaseOperation

logger = get_logger("client-profile-operation")


class ClientProfileOperation(BaseOperation):
    @staticmethod
    async def _sync_client_profile_cache() -> None:
        await refresh_client_profiles_cache()
        await router.publish(MessageTopic.CLIENT_PROFILE, {"action": "refresh"})

    async def _validate_templates(self, db: AsyncSession, templates: dict[ClientProfileTemplateType, int]) -> None:
        for template_type, template_id in templates.items():
            db_template = await get_client_template_by_id(db, template_id)
            if db_template is None:
                await self.raise_error(message=f"Client template {template_id} not found", code=400)
            if db_template.template_type != template_type.value:
                await self.raise_error(
                    message=f"Client template {template_id} is not of type {template_type.value}", code=400
                )

    @staticmethod
    def _build_response(db_profile: ClientProfile, users_count: int = 0) -> ClientProfileResponse:
        response = ClientProfileResponse.model_validate(db_profile)
        response.users_count = users_count
        return response

    async def _get_response(self, db: AsyncSession, db_profile: ClientProfile) -> ClientProfileResponse:
        counts = await count_users_by_client_profile(db, [db_profile.id])
        return self._build_response(db_profile, counts.get(db_profile.id, 0))

    async def create_client_profile(
        self, db: AsyncSession, new_profile: ClientProfileCreate, admin: AdminDetails
    ) -> ClientProfileResponse:
        await self._validate_templates(db, new_profile.templates)

        try:
            db_profile = await create_client_profile(db, new_profile)
        except IntegrityError:
            await self.raise_error("Client profile with this name already exists", 409, db=db)

        logger.info(f'Client profile "{db_profile.name}" created by admin "{admin.username}"')
        await self._sync_client_profile_cache()
        return self._build_response(db_profile)

    async def get_client_profile(self, db: AsyncSession, profile_id: int) -> ClientProfileResponse:
        db_profile = await self.get_validated_client_profile(db, profile_id)
        return await self._get_response(db, db_profile)

    async def get_client_profiles(self, db: AsyncSession, query: ClientProfileListQuery) -> ClientProfileResponseList:
        profiles, count = await get_client_profiles(db, query=query)
        counts = await count_users_by_client_profile(db, [profile.id for profile in profiles])
        return ClientProfileResponseList(
            profiles=[self._build_response(profile, counts.get(profile.id, 0)) for profile in profiles],
            count=count,
        )

    async def get_client_profiles_simple(
        self, db: AsyncSession, query: ClientProfileSimpleListQuery
    ) -> ClientProfilesSimpleResponse:
        rows, total = await get_client_profiles_simple(db=db, query=query)
        return ClientProfilesSimpleResponse(
            profiles=[ClientProfileSimple(id=row[0], name=row[1]) for row in rows], total=total
        )

    async def modify_client_profile(
        self,
        db: AsyncSession,
        profile_id: int,
        modified_profile: ClientProfileModify,
        admin: AdminDetails,
    ) -> ClientProfileResponse:
        db_profile = await self.get_validated_client_profile(db, profile_id)

        if modified_profile.templates:
            await self._validate_templates(db, modified_profile.templates)

        try:
            db_profile = await modify_client_profile(db, db_profile, modified_profile)
        except IntegrityError:
            await self.raise_error("Client profile with this name already exists", 409, db=db)

        logger.info(f'Client profile "{db_profile.name}" modified by admin "{admin.username}"')
        await self._sync_client_profile_cache()
        return await self._get_response(db, db_profile)

    async def remove_client_profile(self, db: AsyncSession, profile_id: int, admin: AdminDetails) -> None:
        db_profile = await self.get_validated_client_profile(db, profile_id)
        name = db_profile.name

        # Users and user templates on this profile fall back to the default delivery
        await remove_client_profiles(db, [db_profile.id])

        logger.info(f'Client profile "{name}" deleted by admin "{admin.username}"')
        await self._sync_client_profile_cache()

    async def bulk_remove_client_profiles(
        self, db: AsyncSession, bulk_profiles: BulkClientProfileSelection, admin: AdminDetails
    ) -> RemoveClientProfilesResponse:
        ids_list = list(bulk_profiles.ids)
        db_profiles, _ = await get_client_profiles(db, ClientProfileListQuery(ids=ids_list, limit=len(ids_list)))

        if set(ids_list) - {profile.id for profile in db_profiles}:
            await self.raise_error(message="Client profile not found", code=404)

        names = [profile.name for profile in db_profiles]
        await remove_client_profiles(db, [profile.id for profile in db_profiles])

        await self._sync_client_profile_cache()
        for name in names:
            logger.info(f'Client profile "{name}" deleted by admin "{admin.username}"')

        return RemoveClientProfilesResponse(profiles=names, count=len(names))

    async def _users_scope_admin_id(self, admin: AdminDetails) -> int | None:
        # Assigning a profile edits users, so it also needs users.update (scope own = only own users)
        try:
            enforce_permission(admin, "users", "update")
        except PermissionDenied as exc:
            await self.raise_error(message=exc.detail, code=403)
        return get_scope_admin_id(admin, "users", "update")

    async def assign_users(
        self, db: AsyncSession, profile_id: int, body: ClientProfileAssignUsers, admin: AdminDetails
    ) -> ClientProfileUsersResponse:
        db_profile = await self.get_validated_client_profile(db, profile_id)
        scope_admin_id = await self._users_scope_admin_id(admin)

        user_ids = list(body.user_ids)
        if set(user_ids) - await get_existing_user_ids(db, user_ids, scope_admin_id):
            await self.raise_error(message="User not found", code=404)

        # One UPDATE; the subscription cache key carries client_profile_id, so these users get fresh configs
        count = await set_users_client_profile(db, db_profile.id, user_ids=user_ids, admin_id=scope_admin_id)

        logger.info(f'{count} user(s) attached to client profile "{db_profile.name}" by admin "{admin.username}"')
        return ClientProfileUsersResponse(count=count)

    async def unassign_users(
        self, db: AsyncSession, profile_id: int, body: ClientProfileUnassignUsers, admin: AdminDetails
    ) -> ClientProfileUsersResponse:
        db_profile = await self.get_validated_client_profile(db, profile_id)
        scope_admin_id = await self._users_scope_admin_id(admin)

        user_ids = None if body.all else list(body.user_ids)
        if user_ids is not None and set(user_ids) - await get_existing_user_ids(db, user_ids, scope_admin_id):
            await self.raise_error(message="User not found", code=404)

        # Only users currently on this profile are detached
        count = await set_users_client_profile(
            db, None, user_ids=user_ids, current_profile_id=db_profile.id, admin_id=scope_admin_id
        )

        logger.info(f'{count} user(s) detached from client profile "{db_profile.name}" by admin "{admin.username}"')
        return ClientProfileUsersResponse(count=count)
