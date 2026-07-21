from fastapi import APIRouter

from app.dependencies.auth import CurrentUserDep
from app.schemas.auth import CurrentUser
from app.schemas.common import ApiResponse, success

router = APIRouter(tags=["auth"])


@router.get("/me", response_model=ApiResponse[CurrentUser])
async def me(user: CurrentUserDep) -> ApiResponse[CurrentUser]:
    return success(
        CurrentUser(
            user_id=user.id,
            username=user.username,
            email=user.email,
            display_name=user.display_name,
            role=user.role,
        )
    )
