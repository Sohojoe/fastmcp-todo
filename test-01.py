"""Demonstration script for the adventure backend prototype."""

from __future__ import annotations

from pathlib import Path
from typing import Iterable

from adventure import (
    BananaQueueManager,
    BananaRenderResult,
    Character,
    GoogleApiKeyMissingError,
    Location,
    NanaBananaRenderer,
    Path as WorldPath,
    WorldObject,
    WorldState,
)


def _build_sample_world() -> WorldState:
    """Create a simple world with two connected locations."""
    world = WorldState()

    meadow = Location(
        key="sunlit-meadow",
        description="A gentle meadow bathed in golden sunlight.",
        objects=[
            WorldObject("Ancient Oak", "A sprawling tree with leaves whispering in the wind."),
            WorldObject("Stone Well", "A weathered well covered in moss."),
        ],
        characters=[
            Character(
                "Lyra the Bard",
                "A cheerful bard tuning her lute.",
                [
                    "Care for a tune to lighten your travels?",
                    "The forest ahead holds both wonder and peril.",
                ],
            )
        ],
        paths=[
            WorldPath("mystic-forest", "A winding trail disappearing into the trees."),
        ],
    )

    forest = Location(
        key="mystic-forest",
        description="Tall pines shroud the forest floor in shifting shadows.",
        objects=[
            WorldObject("Glowing Mushroom", "Its bioluminescence paints the area blue."),
        ],
        characters=[
            Character(
                "Watcher",
                "An enigmatic figure cloaked in emerald robes.",
                ["The trees remember every footstep."],
            )
        ],
        paths=[
            WorldPath("sunlit-meadow", "A narrow path leading back to the sunlit meadow."),
        ],
    )

    world.add_location(meadow)
    world.add_location(forest)
    return world


def _render_with_google(
    queue_manager: BananaQueueManager,
    output_directory: Path,
) -> Iterable[BananaRenderResult]:
    """Process all queued jobs using the Google Imagen backend."""

    try:
        renderer = NanaBananaRenderer.from_environment()
    except GoogleApiKeyMissingError:
        print(
            "Google API key missing – set GOOGLE_API_KEY or GEMINI_API_KEY to render real images."
        )
        yield from _simulate_banana_worker(queue_manager, output_directory)
        return

    for result in queue_manager.drain(renderer, output_directory):
        yield result


def _simulate_banana_worker(
    queue_manager: BananaQueueManager,
    output_directory: Path,
) -> Iterable[BananaRenderResult]:
    """Fallback worker that emits human-readable placeholders."""

    output_directory.mkdir(parents=True, exist_ok=True)

    while True:
        request = queue_manager.dequeue_request(block=False)
        if request is None:
            break

        image_path = output_directory / f"{request.task_id}.txt"
        image_path.write_text(
            "\n".join(
                [
                    f"Rendered location: {request.location['description']}",
                    f"View: {request.view}",
                    "Objects: "
                    + ", ".join(obj["name"] for obj in request.location.get("objects", [])),
                    "Characters: "
                    + ", ".join(character["name"] for character in request.location.get("characters", [])),
                    f"Additional prompt: {request.additional_prompt or 'None'}",
                ]
            )
        )

        result = BananaRenderResult(
            task_id=request.task_id,
            image_path=str(image_path),
            metadata={
                "location_key": request.location.get("key"),
                "reference_images": request.reference_images,
            },
        )
        queue_manager.submit_result(result)
        yield result


def main() -> None:
    world = _build_sample_world()
    queue_manager = BananaQueueManager()

    render_payload = world.render_payload(
        view="wide establishing shot facing north",
        reference_images=["concepts/meadow.png", "concepts/lyra.png"],
        additional_prompt="maintain Lyra's outfit and color palette",
    )
    request = queue_manager.enqueue_payload(render_payload)
    print(f"Enqueued render request {request.task_id} for location {request.location['key']}")

    output_directory = Path("renders")
    for result in _render_with_google(queue_manager, output_directory):
        print(f"Render artifact available at {result.image_path}")

    while queue_manager.has_results():
        result = queue_manager.retrieve_result()
        if result is None:
            break
        print(
            "Result ready:",
            result.task_id,
            result.metadata.get("location_key"),
            "->",
            result.image_path,
        )


if __name__ == "__main__":  # pragma: no cover - manual script
    main()
