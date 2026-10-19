"""收藏与错题本接口（用例 3.5）

学生可把资料、重点题收藏到本子；自测答错的题由 4.6 判分调用 `POST /mistakes` 自动入错题本。
收藏资料与错题共用 collections 表，用 item_type（material / question）区分。
"""
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from ..database import get_db
from ..models.models import Collection, Material, User
from ..schemas.schemas import CollectionCreate, CollectionOut, MistakeBatchIn
from ..utils.security import get_current_user

router = APIRouter()

ITEM_TYPES = ("material", "question")


def _get_own_collection(db: Session, user: User, collection_id: int) -> Collection:
    item = (
        db.query(Collection)
        .filter(Collection.id == collection_id, Collection.user_id == user.id)
        .first()
    )
    if item is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="收藏不存在")
    return item


@router.get("", response_model=list[CollectionOut], summary="收藏与错题本列表（可按类型/来源筛选）")
def list_collections(
    item_type: str | None = None,
    source: str | None = None,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    query = db.query(Collection).filter(Collection.user_id == user.id)
    if item_type:
        query = query.filter(Collection.item_type == item_type)
    if source:
        query = query.filter(Collection.source == source)
    return query.order_by(Collection.id.desc()).all()


@router.post(
    "",
    response_model=CollectionOut,
    status_code=status.HTTP_201_CREATED,
    summary="手动收藏资料或题目",
)
def add_collection(
    payload: CollectionCreate,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    if payload.item_type not in ITEM_TYPES:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"item_type 必须是：{'/'.join(ITEM_TYPES)}",
        )

    if payload.item_type == "material":
        material = (
            db.query(Material)
            .filter(Material.id == payload.material_id, Material.user_id == user.id)
            .first()
        )
        if material is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="资料不存在")
        # 同一份资料重复收藏时直接返回已有的，不报错也不重复占格子
        exists = (
            db.query(Collection)
            .filter(
                Collection.user_id == user.id,
                Collection.item_type == "material",
                Collection.material_id == material.id,
            )
            .first()
        )
        if exists is not None:
            return exists
        item = Collection(
            user_id=user.id,
            item_type="material",
            material_id=material.id,
            title=payload.title.strip() or material.title,
            source="manual",
        )
    else:
        title = payload.title.strip()
        if not title:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="题目内容不能为空")
        item = Collection(
            user_id=user.id,
            item_type="question",
            title=title,
            content=payload.content,
            source="manual",
        )

    db.add(item)
    db.commit()
    db.refresh(item)
    return item


@router.post(
    "/mistakes",
    response_model=list[CollectionOut],
    status_code=status.HTTP_201_CREATED,
    summary="自测答错的题批量入错题本（供 4.6 自测判分调用）",
)
def add_mistakes(
    payload: MistakeBatchIn,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """判分后把答错的题写进错题本；同一用户下题干相同的题只记一次（不重复堆积）"""
    created: list[Collection] = []
    seen: set[str] = set()
    for mistake in payload.mistakes:
        title = mistake.title.strip()
        if not title or title in seen:
            continue
        # 本批新加的 item 尚未 flush，查库看不到彼此，用集合兜住同请求内的重复题干
        seen.add(title)
        exists = (
            db.query(Collection)
            .filter(
                Collection.user_id == user.id,
                Collection.item_type == "question",
                Collection.title == title,
            )
            .first()
        )
        if exists is not None:
            continue
        item = Collection(
            user_id=user.id,
            item_type="question",
            title=title,
            content=mistake.content,
            source="quiz",
        )
        db.add(item)
        created.append(item)

    db.commit()
    for item in created:
        db.refresh(item)
    return created


@router.delete("/{collection_id}", summary="移除收藏 / 错题")
def remove_collection(
    collection_id: int,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    item = _get_own_collection(db, user, collection_id)
    db.delete(item)
    db.commit()
    return {"ok": True}
