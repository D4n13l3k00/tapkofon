import asyncio

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from telethon import functions, types
from telethon.utils import get_input_user

from ..media import avatar_image
from ..preferences import get_preferences
from ..runtime import authorized, entity_id, get_runtime
from ..views import render

router = APIRouter(dependencies=[Depends(authorized)])

STATUSES = {
    types.UserStatusEmpty: "Ничего",
    types.UserStatusOnline: "Онлайн",
    types.UserStatusOffline: "Оффлайн",
    types.UserStatusRecently: "Недавно",
    types.UserStatusLastWeek: "Был на этой неделе",
    types.UserStatusLastMonth: "Был в этом месяце",
}


@router.get("/user/{id}/avatar")
async def avatar(request: Request, id: str):
    runtime = get_runtime(request)
    data = await runtime.client.download_profile_photo(entity_id(id), file=bytes)
    if not data:
        raise HTTPException(404, "У пользователя нет аватара")
    image = await asyncio.to_thread(
        avatar_image,
        data,
        runtime,
        get_preferences(request).image_size,
        request.state.common,
    )
    return Response(image, media_type=f"image/{request.state.common.pic_format}")


@router.get("/user/{id}")
async def user_info(request: Request, id: str):
    client = get_runtime(request).client
    user = await client.get_entity(entity_id(id))
    if not isinstance(user, types.User):
        raise HTTPException(400, "Это не профиль пользователя")
    result = await client(functions.users.GetFullUserRequest(id=get_input_user(user)))
    return render(
        request,
        "user.html",
        user=user,
        user_full=result.full_user,
        status=STATUSES.get(type(user.status), "Неизвестно"),
    )
