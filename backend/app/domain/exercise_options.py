"""Stable Unshaken exercise taxonomy and ExerciseDB normalization."""

from typing import Final

EQUIPMENT: Final[dict[str, str]] = {
    "barbell": "Barbell",
    "dumbbell": "Dumbbell",
    "kettlebell": "Kettlebell",
    "resistance_band": "Resistance band",
    "cable": "Cable",
    "machine": "Machine",
    "bodyweight": "Bodyweight",
    "cardio_machine": "Cardio machine",
    "medicine_ball": "Medicine ball",
    "suspension_trainer": "Suspension trainer",
    "other": "Other",
}

BODY_PARTS: Final[dict[str, str]] = {
    "full_body": "Full body",
    "chest": "Chest",
    "back": "Back",
    "shoulders": "Shoulders",
    "arms": "Arms",
    "core": "Core",
    "glutes": "Glutes",
    "legs": "Legs",
    "calves": "Calves",
    "cardio": "Cardio",
    "mobility": "Mobility",
    "other": "Other",
}

MEASUREMENT_TYPES: Final[dict[str, str]] = {"reps": "Repetitions", "duration": "Duration"}

_EQUIPMENT_ALIASES = {
    "barbell": "barbell",
    "dumbbell": "dumbbell",
    "kettlebell": "kettlebell",
    "resistance band": "resistance_band",
    "band": "resistance_band",
    "cable": "cable",
    "leverage machine": "machine",
    "smith machine": "machine",
    "sled machine": "machine",
    "body weight": "bodyweight",
    "bodyweight": "bodyweight",
    "stationary bike": "cardio_machine",
    "elliptical machine": "cardio_machine",
    "treadmill": "cardio_machine",
    "medicine ball": "medicine_ball",
    "stability ball": "other",
    "assisted": "machine",
}

_BODY_PART_ALIASES = {
    "chest": "chest",
    "back": "back",
    "shoulders": "shoulders",
    "upper arms": "arms",
    "lower arms": "arms",
    "waist": "core",
    "upper legs": "legs",
    "lower legs": "calves",
    "cardio": "cardio",
    "neck": "other",
}


def map_equipment(value: str | None) -> str:
    """Map provider taxonomy to a stable key; unknown values deliberately become other."""
    return _EQUIPMENT_ALIASES.get((value or "").strip().casefold(), "other")


def map_body_part(value: str | None) -> str:
    """Map provider taxonomy to a stable key; unknown values deliberately become other."""
    return _BODY_PART_ALIASES.get((value or "").strip().casefold(), "other")
