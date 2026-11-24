"""Authenticated recipe photo and cooking history endpoints."""

import json
from dataclasses import asdict
from typing import Literal

from fastapi import APIRouter, Depends, Header, Query
from fastapi.responses import Response
from sqlalchemy import select, update
from sqlalchemy.orm import Session

from stock_manager.api import media
from stock_manager.api.db import get_session
from stock_manager.api.errors import APIError
from stock_manager.api.models import RecipePhoto, RecipeUsageHistory
from stock_manager.api.photo_schemas import (
    CookHistoryEntry, CoverUpdate, PhotoUpdate, RecipeCover, RecipePhotoResponse, RecipePhotosResponse,
)
from stock_manager.api.photo_services import (
    ensure_group_capacity, get_photo_recipe, next_position, photo_response, select_cover, validate_step,
)
from stock_manager.api.uploads import PhotoUpload, read_photo_upload


router = APIRouter(tags=["Recipes"])


def _get_photo(db: Session, recipe_id: int, photo_id: int) -> RecipePhoto:
    photo = db.scalar(select(RecipePhoto).where(
        RecipePhoto.recipe_id == recipe_id, RecipePhoto.id == photo_id,
    ))
    if photo is None:
        raise APIError(404, "photo_not_found", "Recipe photo not found")
    return photo


def _recipe_photos(db: Session, recipe_id: int) -> list[RecipePhoto]:
    photos = db.scalars(select(RecipePhoto).where(RecipePhoto.recipe_id == recipe_id))
    return sorted(photos, key=lambda p: (
        p.usage_history_id is not None, p.step_number is not None,
        p.step_number if p.step_number is not None else 0, p.position, p.id,
    ))


@router.get("/recipes/{recipe_id}/photos", response_model=RecipePhotosResponse)
def list_photos(recipe_id: int, db: Session = Depends(get_session)):
    get_photo_recipe(db, recipe_id)
    media.require_media()
    photos = _recipe_photos(db, recipe_id)
    cover = select_cover(photos)
    return RecipePhotosResponse(
        cover_mode=cover.cover_mode, cover=cover.cover, photos=[photo_response(p) for p in photos],
    )


@router.post(
    "/recipes/{recipe_id}/photos", response_model=RecipePhotoResponse, status_code=201,
    openapi_extra={"requestBody": {"required": True, "content": {"multipart/form-data": {"schema": {
        "type": "object",
        "required": ["file"],
        "properties": {
            "file": {"type": "string", "format": "binary"},
            "step_number": {"type": "integer"},
            "usage_history_id": {"type": "integer"},
        },
    }}}}},
)
@media.file_transaction()
def add_photo(
    recipe_id: int, upload: PhotoUpload = Depends(read_photo_upload), db: Session = Depends(get_session),
):
    get_photo_recipe(db, recipe_id, lock=True)
    media.require_media()
    step_number, usage_history_id = upload.step_number, upload.usage_history_id
    if step_number is not None and usage_history_id is not None:
        raise APIError(422, "photo_group_invalid", "A photo can belong to a step or cook record")
    if step_number is not None:
        validate_step(db, recipe_id, step_number)
    if usage_history_id is not None and db.scalar(select(RecipeUsageHistory.id).where(
        RecipeUsageHistory.id == usage_history_id, RecipeUsageHistory.recipe_id == recipe_id,
        RecipeUsageHistory.event_type == "cooked",
    )) is None:
        raise APIError(422, "photo_cook_record_invalid", "Unknown cooking record")
    ensure_group_capacity(db, recipe_id, step_number, usage_history_id)
    position = next_position(db, recipe_id, step_number, usage_history_id)
    stored = media.store_image(upload.data)
    try:
        photo = RecipePhoto(
            recipe_id=recipe_id, origin="user", step_number=step_number,
            usage_history_id=usage_history_id, position=position, **asdict(stored),
        )
        db.add(photo)
        db.commit()
    except Exception:
        db.rollback()
        media.delete_files_if_unused(db, stored.sha256)
        raise
    return photo_response(photo)


@router.patch("/recipes/{recipe_id}/photos/{photo_id}", response_model=RecipePhotoResponse)
@media.file_transaction()
def patch_photo(recipe_id: int, photo_id: int, data: PhotoUpdate, db: Session = Depends(get_session)):
    get_photo_recipe(db, recipe_id, lock=True)
    media.require_media()
    photo = _get_photo(db, recipe_id, photo_id)
    changes = data.model_dump(exclude_unset=True)
    if "hidden" in changes and photo.origin != "howtocook":
        raise APIError(422, "photo_hidden_source_only", "Only source photos can be hidden")
    if changes.get("hidden"):
        photo.is_cover = False
    if "step_number" in changes:
        step = changes["step_number"]
        if step is not None:
            if photo.usage_history_id is not None:
                raise APIError(422, "photo_group_invalid", "A photo can belong to a step or cook record")
            validate_step(db, recipe_id, step)
        if step != photo.step_number:
            if photo.origin == "user":
                ensure_group_capacity(db, recipe_id, step, None)
            if "position" not in changes:
                photo.position = next_position(db, recipe_id, step)
    for field, value in changes.items():
        setattr(photo, field, value)
    db.commit()
    return photo_response(photo)


@router.delete("/recipes/{recipe_id}/photos/{photo_id}", status_code=204)
@media.file_transaction()
def delete_photo(recipe_id: int, photo_id: int, db: Session = Depends(get_session)):
    get_photo_recipe(db, recipe_id, lock=True)
    media.require_media()
    photo = _get_photo(db, recipe_id, photo_id)
    if photo.origin != "user":
        raise APIError(409, "photo_source_readonly", "Source photos cannot be deleted")
    sha256 = photo.sha256
    db.delete(photo)
    db.commit()
    media.delete_files_if_unused(db, sha256)


def _clear_cover(db: Session, recipe_id: int) -> None:
    db.execute(update(RecipePhoto).where(
        RecipePhoto.recipe_id == recipe_id, RecipePhoto.is_cover.is_(True),
    ).values(is_cover=False))


@router.put("/recipes/{recipe_id}/cover", response_model=RecipeCover)
@media.file_transaction()
def set_cover(recipe_id: int, data: CoverUpdate, db: Session = Depends(get_session)):
    get_photo_recipe(db, recipe_id, lock=True)
    media.require_media()
    photo = db.scalar(select(RecipePhoto).where(
        RecipePhoto.recipe_id == recipe_id, RecipePhoto.id == data.photo_id,
        RecipePhoto.hidden.is_(False),
    ))
    if photo is None:
        raise APIError(422, "photo_cover_invalid", "Cover must be a visible photo of this recipe")
    _clear_cover(db, recipe_id)
    photo.is_cover = True
    db.commit()
    return select_cover([photo])


@router.delete("/recipes/{recipe_id}/cover", response_model=RecipeCover)
@media.file_transaction()
def clear_cover(recipe_id: int, db: Session = Depends(get_session)):
    get_photo_recipe(db, recipe_id, lock=True)
    media.require_media()
    _clear_cover(db, recipe_id)
    db.commit()
    return select_cover(_recipe_photos(db, recipe_id))


@router.get("/photos/{photo_id}/image")
def get_image(
    photo_id: int, size: Literal["full", "thumb"] = "full",
    if_none_match: str | None = Header(None), db: Session = Depends(get_session),
):
    media.require_media()
    photo = db.get(RecipePhoto, photo_id)
    if photo is None:
        raise APIError(404, "photo_not_found", "Recipe photo not found")
    path = media.image_path(photo.sha256, size)
    if not path.is_file():
        raise APIError(404, "photo_not_found", "Recipe photo not found")
    etag = f'"{photo.sha256}-{size}"'
    headers = {"ETag": etag, "Cache-Control": "private, max-age=31536000, immutable"}
    if if_none_match and any(
        value.strip().removeprefix("W/") in {etag, "*"} for value in if_none_match.split(",")
    ):
        return Response(status_code=304, headers=headers)
    try:
        content = path.read_bytes()
    except FileNotFoundError:
        raise APIError(404, "photo_not_found", "Recipe photo not found") from None
    return Response(content, media_type="image/jpeg", headers=headers)


def _cook_notes(metadata: str | None) -> str | None:
    try:
        data = json.loads(metadata) if metadata else {}
    except ValueError:
        return None
    notes = data.get("notes") if isinstance(data, dict) else None
    return notes if isinstance(notes, str) else None


@router.get("/recipes/{recipe_id}/cook-history", response_model=list[CookHistoryEntry])
def cook_history(
    recipe_id: int, limit: int = Query(20, ge=1, le=100), offset: int = Query(0, ge=0),
    db: Session = Depends(get_session),
):
    get_photo_recipe(db, recipe_id)
    media.require_media()
    records = list(db.scalars(select(RecipeUsageHistory).where(
        RecipeUsageHistory.recipe_id == recipe_id, RecipeUsageHistory.event_type == "cooked",
    ).order_by(RecipeUsageHistory.created_at.desc(), RecipeUsageHistory.id.desc())
        .limit(limit).offset(offset)))
    if not records:
        return []
    grouped = {}
    for photo in db.scalars(select(RecipePhoto).where(
        RecipePhoto.recipe_id == recipe_id,
        RecipePhoto.usage_history_id.in_([record.id for record in records]),
    ).order_by(RecipePhoto.position, RecipePhoto.id)):
        grouped.setdefault(photo.usage_history_id, []).append(photo_response(photo))
    return [
        CookHistoryEntry(id=r.id, created_at=r.created_at, notes=_cook_notes(r.metadata_json),
                         photos=grouped.get(r.id, []))
        for r in records
    ]
