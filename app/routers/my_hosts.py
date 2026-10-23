from fastapi import APIRouter, Depends

from app.db import AsyncSession, get_db
from app.models.admin import AdminDetails
from app.models.my_hosts import MyHostsPolicy, MyHostsResponse, MyHostsUpdate
from app.operation.my_hosts import MyHostsOperation, get_policy
from app.routers.authentication import get_current_session

router = APIRouter(tags=["My Hosts"], prefix="/api/my-hosts")
operator = MyHostsOperation()


@router.get("/policy", response_model=MyHostsPolicy)
async def get_my_hosts_policy(_: AdminDetails = Depends(get_current_session)):
    return await get_policy()


@router.get("", response_model=MyHostsResponse)
async def get_my_hosts(db: AsyncSession = Depends(get_db), admin: AdminDetails = Depends(get_current_session)):
    return await operator.get_hosts(db, admin)


@router.put("", response_model=MyHostsResponse)
async def modify_my_hosts(
    update: MyHostsUpdate,
    db: AsyncSession = Depends(get_db),
    admin: AdminDetails = Depends(get_current_session),
):
    return await operator.modify_hosts(db, admin, update)
