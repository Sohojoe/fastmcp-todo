"""Integration helpers for invoking Google Imagen through nana-banana."""

from __future__ import annotations

import base64
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Mapping, Optional, Sequence

import google.generativeai as genai

from .banana_queue import BananaRenderRequest, BananaRenderResult


class GoogleApiKeyMissingError(RuntimeError):
    """Raised when the Google API key is not configured."""


def _normalise_api_key(api_key: Optional[str]) -> str:
    if api_key:
        return api_key
    for env_key in ("GEMINI_API_KEY", "GOOGLE_API_KEY"):
        value = os.getenv(env_key)
        if value:
            return value
    raise GoogleApiKeyMissingError(
        "Google API key not found. Set the 'GEMINI_API_KEY' or 'GOOGLE_API_KEY' environment variable, "
        "or provide `api_key` explicitly when constructing NanaBananaRenderer."
    )


def _compose_prompt(request: BananaRenderRequest) -> str:
    location = request.location
    description = location.get("description", "An unnamed location")
    objects = ", ".join(obj.get("name", "") for obj in location.get("objects", [])) or "none"
    characters = ", ".join(ch.get("name", "") for ch in location.get("characters", [])) or "none"
    paths = ", ".join(path.get("description", "") for path in location.get("paths", [])) or "none"

    lines = [
        "Create a richly detailed illustration inspired by 1980s text adventure cover art.",
        f"Primary description: {description}.",
        f"Objects present: {objects}.",
        f"Characters present: {characters}.",
        f"Visible paths or exits: {paths}.",
        f"Camera/view directive: {request.view}.",
    ]

    if request.additional_prompt:
        lines.append(f"Additional stylistic guidance: {request.additional_prompt}.")

    if request.reference_images:
        references = ", ".join(request.reference_images)
        lines.append(
            "Incorporate stylistic cues from the following reference concepts (textual guidance only): "
            f"{references}."
        )

    lines.append(
        "Maintain a cohesive retro fantasy aesthetic with warm lighting and painterly textures."
    )
    return "\n".join(lines)


def _ensure_model(model_name: str) -> genai.GenerativeModel:
    if "/" not in model_name:
        model_name = f"models/{model_name}"
    return genai.GenerativeModel(model_name)


def _extract_image_parts(response: genai.types.GenerateContentResponse) -> List[genai.types.Blob]:
    image_parts: List[genai.types.Blob] = []
    for candidate in response.candidates or []:
        content = getattr(candidate, "content", None)
        if not content:
            continue
        for part in getattr(content, "parts", []) or []:
            inline_data = getattr(part, "inline_data", None)
            if inline_data and getattr(inline_data, "mime_type", "").startswith("image/"):
                image_parts.append(inline_data)
    return image_parts


def _blob_to_bytes(blob: genai.types.Blob) -> bytes:
    data = getattr(blob, "data", None)
    if isinstance(data, bytes):
        return data
    if isinstance(data, str):
        # Some responses serialise bytes as base64 encoded strings
        return base64.b64decode(data)
    raise TypeError("Unexpected blob data type returned by Google API")


def _blob_extension(blob: genai.types.Blob) -> str:
    mime = getattr(blob, "mime_type", "")
    if mime == "image/png":
        return ".png"
    if mime in {"image/jpeg", "image/jpg"}:
        return ".jpg"
    if mime == "image/webp":
        return ".webp"
    return ".img"


@dataclass(slots=True)
class NanaBananaRenderer:
    """Render requests via the Google Imagen model."""

    api_key: str
    model_name: str = "imagen-3.0-generate"
    request_timeout: Optional[float] = 90.0
    safety_settings: Optional[Sequence[Mapping[str, str]]] = None

    def __post_init__(self) -> None:
        genai.configure(api_key=self.api_key)
        self._model = _ensure_model(self.model_name)

    @classmethod
    def from_environment(
        cls,
        *,
        model_name: str = "imagen-3.0-generate",
        request_timeout: Optional[float] = 90.0,
        safety_settings: Optional[Sequence[Mapping[str, str]]] = None,
        api_key: Optional[str] = None,
    ) -> "NanaBananaRenderer":
        """Construct a renderer sourcing the API key from environment variables."""

        return cls(
            api_key=_normalise_api_key(api_key),
            model_name=model_name,
            request_timeout=request_timeout,
            safety_settings=safety_settings,
        )

    def render_request_to_file(
        self,
        request: BananaRenderRequest,
        output_directory: Path,
    ) -> BananaRenderResult:
        """Generate an image for ``request`` and persist it to ``output_directory``."""

        prompt = _compose_prompt(request)
        contents: List[Mapping[str, object]] = [
            {
                "role": "user",
                "parts": [{"text": prompt}],
            }
        ]

        response = self._model.generate_content(
            contents,
            safety_settings=self.safety_settings,
            request_options={"timeout": self.request_timeout} if self.request_timeout else None,
        )

        image_parts = _extract_image_parts(response)
        if not image_parts:
            raise RuntimeError("Google API returned no image data for the render request")

        primary_blob = image_parts[0]
        extension = _blob_extension(primary_blob)
        output_directory.mkdir(parents=True, exist_ok=True)
        output_path = output_directory / f"{request.task_id}{extension}"
        output_path.write_bytes(_blob_to_bytes(primary_blob))

        metadata: Dict[str, object] = {
            "location_key": request.location.get("key"),
            "reference_images": list(request.reference_images),
            "model_name": self._model.model_name,
            "model_version": getattr(response, "model_version", None),
        }

        usage_metadata = getattr(response, "usage_metadata", None)
        if usage_metadata is not None:
            usage_dict: Dict[str, object] = {}
            for field_name in ("prompt_token_count", "candidates_token_count", "total_token_count"):
                value = getattr(usage_metadata, field_name, None)
                if value is not None:
                    usage_dict[field_name] = value
            if usage_dict:
                metadata["usage"] = usage_dict

        prompt_feedback = getattr(response, "prompt_feedback", None)
        if prompt_feedback is not None:
            feedback_dict: Dict[str, object] = {}
            block_reason = getattr(prompt_feedback, "block_reason", None)
            if block_reason:
                feedback_dict["block_reason"] = block_reason
            safety_ratings = getattr(prompt_feedback, "safety_ratings", None)
            if safety_ratings:
                feedback_dict["safety_ratings"] = [
                    {
                        "category": getattr(rating, "category", None),
                        "probability": getattr(rating, "probability", None),
                    }
                    for rating in safety_ratings
                ]
            if feedback_dict:
                metadata["prompt_feedback"] = feedback_dict

        metadata["mime_type"] = getattr(primary_blob, "mime_type", None)

        return BananaRenderResult(
            task_id=request.task_id,
            image_path=str(output_path),
            metadata=metadata,
        )


def ensure_renderer(
    *,
    model_name: str = "imagen-3.0-generate",
    request_timeout: Optional[float] = 90.0,
    safety_settings: Optional[Sequence[Mapping[str, str]]] = None,
    api_key: Optional[str] = None,
) -> NanaBananaRenderer:
    """Factory helper mirroring :meth:`NanaBananaRenderer.from_environment`."""

    return NanaBananaRenderer.from_environment(
        model_name=model_name,
        request_timeout=request_timeout,
        safety_settings=safety_settings,
        api_key=api_key,
    )

