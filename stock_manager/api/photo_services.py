"""Queries and transaction helpers shared by recipes and their photos."""

from collections.abc import Iterable

from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from stock_manager.api import media
from stock_manager.api.errors import APIError
from stock_manager.api.models import Recipe, RecipePhoto, RecipeStep
from stock_manager.api.photo_schemas import RecipeCover, RecipePhotoResponse


GROUP_LIMITS = {"gallery": 12, "step": 3, "cooked": 6}


def get_photo_recipe(db: Session, recipe_id: int, *, lock: bool = False) -> Recipe:
    query = select(Recipe).where(Recipe.id == recipe_id)
    recipe = db.scalar(query.with_for_update() if lock else query)
    if recipe is None:
        raise APIError(404, "recipe_not_found", "Recipe not found")
    return recipe


def photo_group(step_number: int | None, usage_history_id: int | None) -> str:
    if usage_history_id is not None:
        return "cooked"
    if step_number is not None:
        return "step"
    return "gallery"


def photo_response(photo: RecipePhoto) -> RecipePhotoResponse:
    image_url = f"/api/photos/{photo.id}/image"
    return RecipePhotoResponse(
        id=photo.id,
        recipe_id=photo.recipe_id,
        origin=photo.origin,
        group=photo_group(photo.step_number, photo.usage_history_id),
        step_number=photo.step_number,
        usage_history_id=photo.usage_history_id,
        position=photo.position,
        is_cover=photo.is_cover,
        hidden=photo.hidden,
        width=photo.width,
        height=photo.height,
        caption=photo.caption,
        created_at=photo.created_at,
        image_url=image_url,
        thumb_url=f"{image_url}?size=thumb",
    )


def cover_from_photo(photo: RecipePhoto) -> RecipeCover:
    return RecipeCover(
        cover_mode="chosen" if photo.is_cover else "auto",
        cover=photo_response(photo),
    )


def _source_order(photo: RecipePhoto) -> tuple[int, bool, int]:
    # Positions are local to each group. The first imported gallery image wins ties.
    return photo.position, photo.step_number is not None, photo.id


def select_cover(photos: Iterable[RecipePhoto]) -> RecipeCover:
    chosen = None
    newest = None
    source = None
    for photo in photos:
        if photo.hidden:
            continue
        if photo.is_cover:
            chosen = photo
            break
        if photo.origin == "user":
            if newest is None or (photo.created_at, photo.id) > (newest.created_at, newest.id):
                newest = photo
        elif source is None or _source_order(photo) < _source_order(source):
            source = photo
    selected = chosen or newest or source
    return cover_from_photo(selected) if selected is not None else RecipeCover()


def load_covers(db: Session, recipe_ids: list[int]) -> dict[int, RecipeCover]:
    if not media.available() or not recipe_ids:
        return {}
    grouped: dict[int, list[RecipePhoto]] = {}
    photos = db.scalars(select(RecipePhoto).where(
        RecipePhoto.recipe_id.in_(recipe_ids), RecipePhoto.hidden.is_(False),
    ))
    for photo in photos:
        grouped.setdefault(photo.recipe_id, []).append(photo)
    return {recipe_id: select_cover(photos) for recipe_id, photos in grouped.items()}


def validate_step(db: Session, recipe_id: int, step_number: int) -> None:
    step_numbers = list(db.scalars(
        select(RecipeStep.step_number).where(RecipeStep.recipe_id == recipe_id)
        .distinct().order_by(RecipeStep.step_number)
    ))
    if step_number not in step_numbers:
        raise APIError(422, "photo_step_invalid", "Unknown recipe step", step_numbers=step_numbers)


def photo_group_filter(recipe_id: int, step_number: int | None, history_id: int | None):
    return (
        RecipePhoto.recipe_id == recipe_id,
        RecipePhoto.step_number == step_number,
        RecipePhoto.usage_history_id == history_id,
    )


def ensure_group_capacity(db: Session, recipe_id: int, step_number: int | None,
                          history_id: int | None) -> None:
    group = photo_group(step_number, history_id)
    limit = GROUP_LIMITS[group]
    count = db.scalar(select(func.count(RecipePhoto.id)).where(
        *photo_group_filter(recipe_id, step_number, history_id), RecipePhoto.origin == "user",
    ))
    if count >= limit:
        raise APIError(422, "photo_limit_reached", "Too many photos", group=group, limit=limit)


def next_position(db: Session, recipe_id: int, step_number: int | None = None,
                  history_id: int | None = None) -> int:
    last = db.scalar(select(func.max(RecipePhoto.position)).where(
        *photo_group_filter(recipe_id, step_number, history_id)
    ))
    return 0 if last is None else last + 1


def move_orphaned_step_photos(db: Session, recipe_id: int, step_numbers: set[int]) -> None:
    photos = list(db.scalars(select(RecipePhoto).where(
        RecipePhoto.recipe_id == recipe_id,
        RecipePhoto.step_number.is_not(None),
        RecipePhoto.step_number.not_in(step_numbers),
    ).order_by(RecipePhoto.step_number, RecipePhoto.position, RecipePhoto.id)))
    if photos:
        end = next_position(db, recipe_id)
        for index, photo in enumerate(photos, start=end):
            photo.step_number = None
            photo.position = index


def delete_recipe_photos(db: Session, recipe_ids: list[int]) -> set[str]:
    match = RecipePhoto.recipe_id.in_(recipe_ids)
    hashes = set(db.scalars(select(RecipePhoto.sha256).where(match)))
    db.execute(delete(RecipePhoto).where(match))
    return hashes
