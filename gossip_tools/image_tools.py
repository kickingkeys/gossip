"""Hermes tool: gossip_generate_image — generate images via Google Gemini."""

import json
import os
import sys
from pathlib import Path

_vendor = Path(__file__).resolve().parent.parent / "vendor" / "hermes-agent"
if str(_vendor) not in sys.path:
    sys.path.insert(0, str(_vendor))

_root = Path(__file__).resolve().parent.parent
if str(_root) not in sys.path:
    sys.path.insert(0, str(_root))

from tools.registry import registry  # noqa: E402

SCHEMA = {
    "name": "gossip_generate_image",
    "description": (
        "Generate an image from a text prompt using Google Gemini. "
        "Returns the file path of the generated image. "
        "Use for gossip-related visuals, memes, or reactions."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "prompt": {
                "type": "string",
                "description": "Text description of the image to generate.",
            },
        },
        "required": ["prompt"],
    },
}


def _handler(args, **kwargs):
    from gossip.logger import log_event, get_current_session_id

    prompt = args.get("prompt", "").strip()
    if not prompt:
        return json.dumps({"error": "prompt is required"})

    api_key = os.getenv("GEMINI_API_KEY") or os.getenv("FAL_KEY")
    if not api_key:
        return json.dumps({"error": "GEMINI_API_KEY not set"})

    try:
        from google import genai

        client = genai.Client(api_key=api_key)

        response = client.models.generate_content(
            model="gemini-2.5-flash-image",
            contents=prompt,
            config=genai.types.GenerateContentConfig(
                response_modalities=["IMAGE", "TEXT"],
            ),
        )

        # Extract image from response
        output_dir = Path(_root) / "data" / "images"
        output_dir.mkdir(parents=True, exist_ok=True)

        import time
        image_path = None

        for part in response.candidates[0].content.parts:
            if part.inline_data and part.inline_data.mime_type.startswith("image/"):
                ext = part.inline_data.mime_type.split("/")[-1]
                if ext == "jpeg":
                    ext = "jpg"
                filename = f"gossip_{int(time.time())}.{ext}"
                image_path = output_dir / filename

                with open(image_path, "wb") as f:
                    f.write(part.inline_data.data)
                break

        if not image_path:
            return json.dumps({"error": "No image generated — model returned text only"})

        log_event(
            event_type="image_generate",
            summary=f"Generated image: {prompt[:80]}",
            payload={"prompt": prompt, "path": str(image_path)},
            session_id=get_current_session_id(),
        )

        return json.dumps({
            "success": True,
            "image_path": str(image_path),
            "prompt": prompt,
        })

    except Exception as e:
        log_event(
            event_type="image_generate",
            event_subtype="error",
            summary=f"Image generation failed: {e}",
            payload={"prompt": prompt, "error": str(e)},
            session_id=get_current_session_id(),
        )
        return json.dumps({"error": str(e)})


def _check():
    api_key = os.getenv("GEMINI_API_KEY") or os.getenv("FAL_KEY")
    return bool(api_key)


registry.register(
    name="gossip_generate_image",
    toolset="gossip",
    schema=SCHEMA,
    handler=_handler,
    check_fn=_check,
    is_async=False,
)
