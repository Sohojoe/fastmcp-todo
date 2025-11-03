"""Core world state models for the adventure backend."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional


@dataclass(slots=True)
class WorldObject:
    """A physical object that can exist within a location."""

    name: str
    description: str

    def as_dict(self) -> Dict[str, str]:
        """Return a JSON-serialisable representation of the object."""
        return {"name": self.name, "description": self.description}


@dataclass(slots=True)
class Character:
    """A character that can appear in a location."""

    name: str
    description: str
    dialogue: List[str] = field(default_factory=list)

    def as_dict(self) -> Dict[str, object]:
        """Return a JSON-serialisable representation of the character."""
        return {
            "name": self.name,
            "description": self.description,
            "dialogue": list(self.dialogue),
        }


@dataclass(slots=True)
class Path:
    """A connection from one location to another."""

    target: str
    description: str

    def as_dict(self) -> Dict[str, str]:
        """Return a JSON-serialisable representation of the path."""
        return {"target": self.target, "description": self.description}


@dataclass(slots=True)
class Location:
    """A location in the adventure world."""

    key: str
    description: str
    objects: List[WorldObject] = field(default_factory=list)
    characters: List[Character] = field(default_factory=list)
    paths: List[Path] = field(default_factory=list)

    def as_dict(self) -> Dict[str, object]:
        """Return a JSON-serialisable representation of the location."""
        return {
            "key": self.key,
            "description": self.description,
            "objects": [obj.as_dict() for obj in self.objects],
            "characters": [character.as_dict() for character in self.characters],
            "paths": [path.as_dict() for path in self.paths],
        }


class WorldState:
    """Holds the current adventure world state."""

    def __init__(self) -> None:
        self._locations: Dict[str, Location] = {}
        self.current_location_key: Optional[str] = None

    # ------------------------------------------------------------------
    # Location management
    # ------------------------------------------------------------------
    def add_location(self, location: Location) -> None:
        """Register a new location in the world."""
        self._locations[location.key] = location
        if self.current_location_key is None:
            self.current_location_key = location.key

    def set_current_location(self, location_key: str) -> None:
        """Switch the current location to ``location_key``."""
        if location_key not in self._locations:
            raise KeyError(f"Unknown location '{location_key}'")
        self.current_location_key = location_key

    # ------------------------------------------------------------------
    # Queries
    # ------------------------------------------------------------------
    def get_location(self, location_key: str) -> Location:
        """Retrieve a location by its key."""
        try:
            return self._locations[location_key]
        except KeyError as exc:
            raise KeyError(f"Unknown location '{location_key}'") from exc

    def get_current_location(self) -> Location:
        """Return the current location object."""
        if self.current_location_key is None:
            raise RuntimeError("No current location has been set")
        return self.get_location(self.current_location_key)

    def move(self, target_location_key: str) -> Location:
        """Move to the specified location and return it."""
        self.set_current_location(target_location_key)
        return self.get_current_location()

    # ------------------------------------------------------------------
    # Serialisation helpers
    # ------------------------------------------------------------------
    def snapshot(self) -> Dict[str, object]:
        """Return a snapshot of the current location's state."""
        location = self.get_current_location()
        return location.as_dict()

    def render_payload(
        self,
        view: str,
        reference_images: Optional[List[str]] = None,
        additional_prompt: Optional[str] = None,
    ) -> Dict[str, object]:
        """Build a payload describing the state for image generation."""

        return {
            "location": self.snapshot(),
            "view": view,
            "reference_images": list(reference_images or []),
            "additional_prompt": additional_prompt,
        }

    # ------------------------------------------------------------------
    # Introspection helpers
    # ------------------------------------------------------------------
    def list_locations(self) -> List[str]:
        """Return a list of all known location keys."""
        return list(self._locations.keys())

    def to_dict(self) -> Dict[str, object]:
        """Return a serialisable representation of the full world state."""
        return {
            "current_location": self.current_location_key,
            "locations": {key: location.as_dict() for key, location in self._locations.items()},
        }
