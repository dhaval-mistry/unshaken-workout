"""Strict request and named response models for Unshaken's private APIs."""

from datetime import datetime
from decimal import Decimal
from typing import Annotated, Literal, Self
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

Equipment = Literal[
    "barbell",
    "dumbbell",
    "kettlebell",
    "resistance_band",
    "cable",
    "machine",
    "bodyweight",
    "cardio_machine",
    "medicine_ball",
    "suspension_trainer",
    "other",
]
BodyPart = Literal[
    "full_body",
    "chest",
    "back",
    "shoulders",
    "arms",
    "core",
    "glutes",
    "legs",
    "calves",
    "cardio",
    "mobility",
    "other",
]
MeasurementType = Literal["reps", "duration"]


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


def _trim(value: str | None) -> str | None:
    return None if value is None else value.strip() or None


def _reject_explicit_null(model: BaseModel, fields: set[str]) -> None:
    for field in fields & model.model_fields_set:
        if getattr(model, field) is None:
            raise ValueError(f"{field} may not be null")


class ProfilePatch(StrictModel):
    display_name: str | None = Field(default=None, min_length=1, max_length=80)
    preferred_weight_unit: Literal["kg", "lb"] | None = None

    @field_validator("display_name", mode="before")
    @classmethod
    def trim_name(cls, value: object) -> object:
        return value.strip() if isinstance(value, str) else value

    @model_validator(mode="after")
    def reject_nulls(self) -> Self:
        _reject_explicit_null(self, {"display_name", "preferred_weight_unit"})
        return self


class CustomExerciseWrite(StrictModel):
    name: str = Field(min_length=1, max_length=120)
    training_type: Literal["strength", "functional", "cardio", "mobility", "other"]
    equipment: Equipment = Field(description="One stable Unshaken equipment category.")
    body_part: BodyPart
    measurement_type: MeasurementType
    instructions: str | None = Field(default=None, max_length=5000)
    notes: str | None = Field(default=None, max_length=2000)

    @field_validator("name", mode="before")
    @classmethod
    def trim_name(cls, value: object) -> object:
        return value.strip() if isinstance(value, str) else value

    @field_validator("instructions", "notes", mode="before")
    @classmethod
    def trim_optional(cls, value: object) -> object:
        return _trim(value) if isinstance(value, str) else value


class CustomExercisePatch(StrictModel):
    name: str | None = Field(default=None, min_length=1, max_length=120)
    training_type: Literal["strength", "functional", "cardio", "mobility", "other"] | None = None
    equipment: Equipment | None = None
    body_part: BodyPart | None = None
    measurement_type: MeasurementType | None = None
    instructions: str | None = Field(default=None, max_length=5000)
    notes: str | None = Field(default=None, max_length=2000)

    @field_validator("name", mode="before")
    @classmethod
    def trim_name(cls, value: object) -> object:
        return value.strip() if isinstance(value, str) else value

    @field_validator("instructions", "notes", mode="before")
    @classmethod
    def trim_optional(cls, value: object) -> object:
        return _trim(value) if isinstance(value, str) else value

    @model_validator(mode="after")
    def reject_nulls(self) -> Self:
        _reject_explicit_null(
            self, {"name", "training_type", "equipment", "body_part", "measurement_type"}
        )
        return self


class PlanCreate(StrictModel):
    name: str = Field(min_length=1, max_length=120)

    @field_validator("name", mode="before")
    @classmethod
    def trim_name(cls, value: object) -> object:
        return value.strip() if isinstance(value, str) else value


class PlanDuplicate(StrictModel):
    name: str | None = Field(default=None, min_length=1, max_length=120)

    @field_validator("name", mode="before")
    @classmethod
    def trim_name(cls, value: object) -> object:
        return value.strip() if isinstance(value, str) else value


class CustomExerciseAdd(StrictModel):
    source_kind: Literal["custom"]
    custom_exercise_id: UUID
    note: str | None = Field(default=None, max_length=2000)

    @field_validator("note", mode="before")
    @classmethod
    def trim_note(cls, value: object) -> object:
        return _trim(value) if isinstance(value, str) else value


class ExternalExerciseAdd(StrictModel):
    source_kind: Literal["external"]
    external_provider: Literal["exercisedb"]
    external_exercise_id: str = Field(min_length=1, max_length=100)
    measurement_type: MeasurementType
    note: str | None = Field(default=None, max_length=2000)

    @field_validator("external_exercise_id", mode="before")
    @classmethod
    def trim_id(cls, value: object) -> object:
        return value.strip() if isinstance(value, str) else value

    @field_validator("note", mode="before")
    @classmethod
    def trim_note(cls, value: object) -> object:
        return _trim(value) if isinstance(value, str) else value


ExerciseAdd = Annotated[CustomExerciseAdd | ExternalExerciseAdd, Field(discriminator="source_kind")]


class NotePatch(StrictModel):
    note: str | None = Field(max_length=2000)

    @field_validator("note", mode="before")
    @classmethod
    def trim_note(cls, value: object) -> object:
        return _trim(value) if isinstance(value, str) else value


class OrderWrite(StrictModel):
    exercise_ids: list[UUID] = Field(max_length=50)


class PlannedSetCreate(StrictModel):
    target_reps: int | None = Field(default=None, ge=1, le=999)
    target_duration_seconds: int | None = Field(default=None, ge=1, le=86400)
    target_weight_kg: Decimal | None = Field(
        default=None, ge=0, le=Decimal("999999.99"), decimal_places=2
    )
    rest_seconds: int = Field(default=120, ge=0, le=3600)


class PlannedSetPatch(StrictModel):
    target_reps: int | None = Field(default=None, ge=1, le=999)
    target_duration_seconds: int | None = Field(default=None, ge=1, le=86400)
    target_weight_kg: Decimal | None = Field(
        default=None, ge=0, le=Decimal("999999.99"), decimal_places=2
    )
    rest_seconds: int | None = Field(default=None, ge=0, le=3600)

    @model_validator(mode="after")
    def reject_null_nonnullable(self) -> Self:
        _reject_explicit_null(self, {"rest_seconds"})
        return self


class SessionCreate(StrictModel):
    source_plan_id: UUID | None = None
    name: str | None = Field(default=None, min_length=1, max_length=120)

    @field_validator("name", mode="before")
    @classmethod
    def trim_name(cls, value: object) -> object:
        return value.strip() if isinstance(value, str) else value


class SessionSetPatch(PlannedSetPatch):
    actual_reps: int | None = Field(default=None, ge=1, le=999)
    actual_duration_seconds: int | None = Field(default=None, ge=1, le=86400)
    actual_weight_kg: Decimal | None = Field(
        default=None, ge=0, le=Decimal("999999.99"), decimal_places=2
    )
    status: Literal["planned", "completed", "skipped"] | None = None

    @model_validator(mode="after")
    def reject_null_status(self) -> Self:
        _reject_explicit_null(self, {"rest_seconds", "status"})
        return self


class ProblemResponse(BaseModel):
    code: str
    message: str
    fields: list[str] | None = None


class ProfileResponse(BaseModel):
    id: UUID
    display_name: str
    email: str
    preferred_weight_unit: Literal["kg", "lb"]
    created_at: datetime
    updated_at: datetime


class CustomExerciseResponse(BaseModel):
    id: UUID
    name: str
    training_type: str
    equipment: Equipment
    body_part: BodyPart
    measurement_type: MeasurementType
    instructions: str | None
    notes: str | None
    archived_at: datetime | None
    created_at: datetime
    updated_at: datetime


class CustomExercisePage(BaseModel):
    items: list[CustomExerciseResponse]
    page: int
    page_size: int
    total: int


class PlannedSetResponse(BaseModel):
    id: UUID
    set_number: int
    measurement_type: MeasurementType
    target_reps: int | None
    target_duration_seconds: int | None
    target_weight_kg: Decimal | None
    rest_seconds: int


class PlanExerciseResponse(BaseModel):
    id: UUID
    exercise_order: int
    source_kind: Literal["custom", "external"]
    custom_exercise_id: UUID | None
    external_provider: str | None
    external_exercise_id: str | None
    exercise_name: str
    body_part: BodyPart
    equipment: Equipment
    measurement_type: MeasurementType
    note: str | None
    sets: list[PlannedSetResponse]


class PlanResponse(BaseModel):
    id: UUID
    name: str
    archived_at: datetime | None
    version: int
    created_at: datetime
    updated_at: datetime
    last_performed_at: datetime | None
    exercises: list[PlanExerciseResponse]


class ExercisePreview(BaseModel):
    name: str
    set_count: int
    measurement_type: MeasurementType


class PlanSummary(BaseModel):
    id: UUID
    name: str
    archived_at: datetime | None
    version: int
    exercise_count: int
    created_at: datetime
    updated_at: datetime
    last_performed_at: datetime | None
    exercise_preview: list[ExercisePreview]


class PlanPage(BaseModel):
    items: list[PlanSummary]
    page: int
    page_size: int
    total: int


class SessionSetResponse(PlannedSetResponse):
    actual_reps: int | None
    actual_duration_seconds: int | None
    actual_weight_kg: Decimal | None
    status: Literal["planned", "completed", "skipped"]
    completed_at: datetime | None


class SessionExerciseResponse(PlanExerciseResponse):
    sets: list[SessionSetResponse]  # type: ignore[assignment]


class SessionResponse(BaseModel):
    id: UUID
    name: str | None
    source_plan_id: UUID | None
    status: Literal["in_progress", "finished", "abandoned"]
    started_at: datetime
    finished_at: datetime | None
    total_time_seconds: int | None
    version: int
    created_at: datetime
    updated_at: datetime
    exercises: list[SessionExerciseResponse]


class SessionSummary(BaseModel):
    id: UUID
    name: str | None
    source_plan_id: UUID | None
    status: Literal["in_progress", "finished", "abandoned"]
    started_at: datetime
    finished_at: datetime | None
    total_time_seconds: int | None
    version: int


class SessionPage(BaseModel):
    items: list[SessionSummary]
    page: int
    page_size: int
    total: int


class Option(BaseModel):
    key: str
    label: str


class ExerciseOptionsResponse(BaseModel):
    equipment: list[Option]
    body_parts: list[Option]
    measurement_types: list[Option]


class CatalogItem(BaseModel):
    source_kind: Literal["custom", "external"]
    custom_exercise_id: UUID | None = None
    external_provider: str | None = None
    external_exercise_id: str | None = None
    name: str
    body_part: BodyPart
    equipment: Equipment
    measurement_type: MeasurementType | None
    measurement_type_required_on_selection: bool
    is_archived: Literal[False] = False
    provider_attribution: str | None = None


class CatalogPage(BaseModel):
    items: list[CatalogItem]
    page_size: int
    next_cursor: str | None
    provider_status: Literal["available", "degraded", "not_requested"]


class LatestPerformanceSet(BaseModel):
    set_number: int
    actual_reps: int | None
    actual_duration_seconds: int | None
    actual_weight_kg: Decimal | None
    status: str


class LatestPerformanceItem(BaseModel):
    session_id: UUID
    session_name: str | None
    finished_at: datetime
    session_exercise_id: UUID
    exercise_name: str
    measurement_type: MeasurementType
    sets: list[LatestPerformanceSet]


class LatestPerformanceResponse(BaseModel):
    item: LatestPerformanceItem | None
