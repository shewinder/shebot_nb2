from typing import List

from fastapi import APIRouter
from pydantic import BaseModel
from hoshino.modules.infopush._data import SubscribeRecord
from hoshino.modules.infopush._model import refresh_subdata

def sub_to_dict(sub: SubscribeRecord) -> dict:
    return {
        "checker": sub.checker,
        "remark": sub.remark,
        "url": sub.url,
        "date": sub.date,
        "creator": sub.creator,
        "group": sub.group,
        "id": sub.id,
    }


router = APIRouter(prefix="/infopush")


@router.get("/list/all")
async def list_all_subs():
    return {"subs": [sub_to_dict(sub) for sub in SubscribeRecord.select()]}


@router.get("/list/{user_id}")
async def list_user_subscribe(user_id: str) -> List[dict]:
    return {
        "subs": [
            sub_to_dict(sub)
            for sub in SubscribeRecord.select().where(
                SubscribeRecord.creator == user_id
            )
        ]
    }


class DeleteForm(BaseModel):
    ids: List[int]

@router.post("/delete_by_ids")
async def delete_by_ids(form: DeleteForm):
    cnt = 0
    for id_ in form.ids:
        SubscribeRecord.delete_by_id(id_)
        cnt = cnt + 1
    refresh_subdata()
    return {"status": 200, "data": f"{cnt} items deleted"}

# @router.post("/delete")
# async def batch_delete(form: DeleteForm):
#     cnt = 0
#     for item in form.item:
#         try:
#             SubscribeRecord.delete().where(
#                 SubscribeRecord.id == item.id,
#             ).execute()
#             cnt = cnt + 1
#         except:
#             raise


#     for item in form.items:
#         try:
#             SubscribeRecord.delete().where(
#                 SubscribeRecord.url == item.url,
#                 SubscribeRecord.group == item.group,
#                 SubscribeRecord.creator == item.creator,
#             ).execute()
#             cnt = cnt + 1
#         except:
#             raise
#     return {"status": f"{cnt} items deleted"}


class AddItem(BaseModel):
    url: str
    checker: str
    remark: str
    group: str
    creator: str


class AddForm(BaseModel):
    items: List[AddItem]


@router.post("/add")
async def batch_add(form: AddForm):
    subs = [
        SubscribeRecord(
            url=item.url,
            checker=item.checker,
            remark=item.remark,
            group=item.group,
            creator=item.creator,
        )
        for item in form.items
    ]
    SubscribeRecord.bulk_create(subs)
    refresh_subdata()
    return {"status": 200, "data": "SUCCESS"}
