from typing import Tuple, Dict, Any, Optional

# Lazy import to avoid forcing the dependency if caller never needs vision.
try:
    import google.generativeai as genai
except ImportError:  # pragma: no cover – handled at runtime
    genai = None  # type: ignore

class GeminiVisionService:
    """Stub for future visual analysis using Gemini Pro-Vision.

    analyse_clip is intended to receive a path to a video clip plus its transcript snippet
    and return a pair (extend_before, extend_after) in seconds.
    Currently returns (0.0, 0.0) so the pipeline can call it without affecting timing.
    """

    def __init__(self, api_key: str | None = None, model_name: str = "models/gemini-2.5-flash") -> None:
        # Deferred import of google.generativeai until real implementation
        self.api_key = api_key
        self.model_name = model_name

    async def analyse_clip(
        self,
        clip_path: str,
        transcript_slice: Optional[str] = None,
        max_extension_seconds: float = 3.0,
    ) -> Tuple[float, float]:
        """Analyse *clip_path* with Gemini Vision to decide if the clip needs more context.

        The model is asked to return JSON with two positive floats:

            {"extend_before": <seconds>, "extend_after": <seconds>}  

        • *extend_before* – how many seconds to prepend before *clip_path*'s current start.
        • *extend_after*  – how many seconds to append after its current end.

        If the call fails or the response is malformed we fall back to (0.0, 0.0).
        """
        # Quick bail-out when the dependency is missing or the key is not set.
        if genai is None or not self.api_key:
            return 0.0, 0.0

        # Configure only once.
        genai.configure(api_key=self.api_key)

        try:
            model = genai.GenerativeModel(self.model_name)

            system_prompt = (
                "You are a video-editing assistant. "
                "Given a gameplay video clip and its transcript snippet, "
                "decide whether viewers need additional visual context (seconds) *before* or *after* the current clip. "
                "Return ONLY JSON in the form: {\"extend_before\": float, \"extend_after\": float}. "
                f"Each value must be 0–{max_extension_seconds}. Use 0 when no extension is required."
            )

            # --- Build content in the recommended order: media first, then text ---

            # 1) Video bytes
            with open(clip_path, "rb") as f:
                video_bytes = f.read()

            content: list[Any] = [
                {"mime_type": "video/mp4", "data": video_bytes}
            ]

            # 2) Metadata block (so the model knows its constraints)
            metadata_json = json.dumps({
                "max_extension_seconds": max_extension_seconds,
                "transcript_provided": bool(transcript_slice),
            })
            content.append(f"metadata:\n{metadata_json}")

            # 3) Optional transcript snippet
            if transcript_slice:
                content.append("voice_line_transcript:\n" + transcript_slice)

            # 4) Final system prompt / instructions
            content.append(system_prompt)

            response = await model.generate_content_async(content)  # type: ignore[attr-defined]

            raw_text = response.text if hasattr(response, "text") else str(response)

            # Attempt to extract the JSON object.
            import json, re

            # Find first {...} block.
            m = re.search(r"\{.*?\}", raw_text)
            if not m:
                return 0.0, 0.0

            data = json.loads(m.group(0))
            extend_before = float(max(0.0, min(float(data.get("extend_before", 0.0)), max_extension_seconds)))
            extend_after = float(max(0.0, min(float(data.get("extend_after", 0.0)), max_extension_seconds)))

            return extend_before, extend_after
        except Exception:
            # Any failure → play it safe, no extension.
            return 0.0, 0.0 