"""Queue primitives for sending render tasks to nana-banana."""

from __future__ import annotations

import queue
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional, TYPE_CHECKING

if TYPE_CHECKING:  # pragma: no cover - only used for type checkers
    from .nana_banana import NanaBananaRenderer


@dataclass(slots=True)
class BananaRenderRequest:
    """A request to render a scene for the current world state."""

    task_id: str
    location: Dict[str, object]
    view: str
    reference_images: List[str] = field(default_factory=list)
    additional_prompt: Optional[str] = None

    @classmethod
    def from_payload(
        cls,
        payload: Dict[str, object],
        task_id: Optional[str] = None,
    ) -> "BananaRenderRequest":
        """Create a request from a payload produced by ``WorldState.render_payload``."""

        task_id = task_id or str(uuid.uuid4())
        return cls(
            task_id=task_id,
            location=payload["location"],
            view=payload["view"],
            reference_images=list(payload.get("reference_images", [])),
            additional_prompt=payload.get("additional_prompt"),
        )


@dataclass(slots=True)
class BananaRenderResult:
    """The result produced by nana-banana after rendering."""

    task_id: str
    image_path: str
    metadata: Dict[str, object] = field(default_factory=dict)


class BananaQueueManager:
    """In-memory queue manager for nana-banana render jobs."""

    def __init__(self) -> None:
        self._banana_in_queue: "queue.Queue[BananaRenderRequest]" = queue.Queue()
        self._banana_out_queue: "queue.Queue[BananaRenderResult]" = queue.Queue()

    # ------------------------------------------------------------------
    # Convenience orchestration helpers
    # ------------------------------------------------------------------
    def process_next_request(
        self,
        renderer: "NanaBananaRenderer",
        output_directory: "Path",
        *,
        block: bool = False,
        timeout: Optional[float] = None,
    ) -> Optional[BananaRenderResult]:
        """Process a single queued request using ``renderer``.

        Parameters
        ----------
        renderer:
            The :class:`~adventure.nana_banana.NanaBananaRenderer` responsible for
            invoking the Google image generation API.
        output_directory:
            Filesystem directory where rendered images should be written.
        block, timeout:
            Passed directly to :meth:`dequeue_request` allowing callers to wait for
            work when integrating into worker loops.

        Returns
        -------
        Optional[BananaRenderResult]
            The produced render result if a request was available, otherwise
            ``None``.
        """

        request = self.dequeue_request(block=block, timeout=timeout)
        if request is None:
            return None

        result = renderer.render_request_to_file(request, output_directory)
        self.submit_result(result)
        return result

    def drain(
        self,
        renderer: "NanaBananaRenderer",
        output_directory: "Path",
    ) -> List[BananaRenderResult]:
        """Process all currently queued requests using ``renderer``.

        This helper is primarily intended for scripts/tests where a synchronous
        drain of the queue is sufficient.
        """

        results: List[BananaRenderResult] = []
        while True:
            request = self.dequeue_request(block=False)
            if request is None:
                break
            result = renderer.render_request_to_file(request, output_directory)
            self.submit_result(result)
            results.append(result)
        return results

    # ------------------------------------------------------------------
    # Queue APIs
    # ------------------------------------------------------------------
    def enqueue(self, request: BananaRenderRequest) -> None:
        """Submit a render request to the input queue."""
        self._banana_in_queue.put(request)

    def enqueue_payload(
        self,
        payload: Dict[str, object],
        task_id: Optional[str] = None,
    ) -> BananaRenderRequest:
        """Create and enqueue a render request from a payload."""
        request = BananaRenderRequest.from_payload(payload, task_id=task_id)
        self.enqueue(request)
        return request

    def dequeue_request(
        self,
        block: bool = False,
        timeout: Optional[float] = None,
    ) -> Optional[BananaRenderRequest]:
        """Retrieve the next request awaiting processing."""
        try:
            return self._banana_in_queue.get(block=block, timeout=timeout)
        except queue.Empty:
            return None

    def submit_result(self, result: BananaRenderResult) -> None:
        """Push a completed render result onto the output queue."""
        self._banana_out_queue.put(result)

    def retrieve_result(
        self,
        block: bool = False,
        timeout: Optional[float] = None,
    ) -> Optional[BananaRenderResult]:
        """Fetch the next available render result."""
        try:
            return self._banana_out_queue.get(block=block, timeout=timeout)
        except queue.Empty:
            return None

    # ------------------------------------------------------------------
    # Convenience helpers
    # ------------------------------------------------------------------
    def has_pending_requests(self) -> bool:
        """Return ``True`` if there are requests awaiting processing."""
        return not self._banana_in_queue.empty()

    def has_results(self) -> bool:
        """Return ``True`` if there are completed results."""
        return not self._banana_out_queue.empty()

    def clear(self) -> None:
        """Empty both the input and output queues."""
        while self.has_pending_requests():
            self._banana_in_queue.get_nowait()
        while self.has_results():
            self._banana_out_queue.get_nowait()
