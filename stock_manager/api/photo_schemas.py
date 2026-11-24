"""Request and response models for recipe photos."""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field, field_validator


CoverMode = Literal["chosen", "auto", "none"]


class RecipePhotoResponse(BaseModel):
    id: int
    recipe_id: int
    origin: Literal["howtocook", "user"]
    group: Literal["gallery", "step", "cooked"]
    step_number: int | None
    usage_history_id: int | None
    position: int
    is_cover: bool
    hidden: bool
    width: int
    height: int
    caption: str | None
    created_at: datetime
    image_url: str
    thumb_url: str

    model_config = {"from_attributes": True}


class RecipeCover(BaseModel):
    cover_mode: CoverMode = "none"
    cover: RecipePhotoResponse | None = None


class RecipePhotosResponse(RecipeCover):
    photos: list[RecipePhotoResponse]


class PhotoUpdate(BaseModel):
    position: int | None = Field(None, ge=0)
    step_number: int | None = None
    hidden: bool | None = None
    caption: str | None = Field(None, max_length=255)

    @field_validator("position", "hidden")
    @classmethod
    def reject_null(cls, value, info):
        if value is None:
            raise ValueError(f"{info.field_name} cannot be null")
        return value


class CoverUpdate(BaseModel):
    photo_id: int


class CookHistoryEntry(BaseModel):
    id: int
    created_at: datetime
    notes: str | None
    photos: list[RecipePhotoResponse]
