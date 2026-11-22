"""Local SLM Service for Contextual Analysis, Name Variant Linking, and Summarization.

Interacts strictly with local runtimes (e.g., Ollama / llama.cpp on 127.0.0.1).
Guarantees:
- Zero external API or cloud calls.
- Strict Pydantic schema validation for all structured outputs.
- Graceful degraded-mode fallback on timeout, connection refusal, or malformed JSON.
- Never logs raw document text or sensitive PII.
"""

import json
import logging
from typing import Any, Dict, List, Optional
import httpx

from app.core.config import settings
from app.schemas.entity import SLMAnalysisResponse

logger = logging.getLogger(__name__)


class ModelService:
    """Manages communication with local SLM inference engine (e.g. Ollama)."""

    @classmethod
    def check_availability(cls) -> bool:
        """Ping local SLM server to verify reachability. Returns False if offline or times out."""
        url = f"{settings.LOCAL_SLM_URL.rstrip('/')}/api/version"
        try:
            with httpx.Client(timeout=1.0) as client:
                res = client.get(url)
                return res.status_code == 200
        except Exception:
            # Server offline, connection refused, or timed out
            return False

    @classmethod
    def analyze_context(
        cls,
        text_snippet: str,
        detected_names: List[str],
    ) -> Optional[SLMAnalysisResponse]:
        """Request local SLM to analyze detected names and context for variant linkages and missed PII.
        
        Returns parsed and schema-validated SLMAnalysisResponse, or None if SLM is unavailable/fails.
        """
        if not detected_names and not text_snippet.strip():
            return None

        # Build prompt enforcing strict JSON output conforming to SLMAnalysisResponse
        prompt = (
            "You are a local privacy and entity linking assistant. Analyze the following document text "
            "and list of detected entity mentions. Identify if any detected names represent variants "
            "of the same person (e.g. initial-to-full name, title with surname), or if any person names "
            "were missed.\n\n"
            "Return ONLY a valid JSON object matching this schema:\n"
            "{\n"
            '  "suggested_candidates": [\n'
            '    {"text": "name", "type": "PERSON", "reason": "justification"}\n'
            "  ],\n"
            '  "suggested_links": [\n'
            '    {"source_text": "R. Sharma", "target_text": "Richa Sharma", "relation_type": "INITIAL", "confidence": 0.85, "reason": "Shared surname and matching initial"}\n'
            "  ],\n"
            '  "notes": "optional observations"\n'
            "}\n\n"
            f"Detected names: {json.dumps(detected_names)}\n"
            f"Document snippet:\n\"\"\"\n{text_snippet[:1500]}\n\"\"\"\n"
        )

        url = f"{settings.LOCAL_SLM_URL.rstrip('/')}/api/generate"
        payload = {
            "model": settings.SLM_MODEL_NAME,
            "prompt": prompt,
            "stream": False,
            "format": "json",
            "options": {
                "temperature": 0.1,
                "top_p": 0.9,
            },
        }

        try:
            with httpx.Client(timeout=settings.SLM_TIMEOUT_SECONDS) as client:
                response = client.post(url, json=payload)
                if response.status_code != 200:
                    logger.warning(
                        "Local SLM returned non-200 status code: %d", response.status_code
                    )
                    return None

                data = response.json()
                raw_response_text = data.get("response", "")
                if not raw_response_text:
                    return None

                parsed_json = json.loads(raw_response_text)
                # Strict validation against Pydantic schema
                validated = SLMAnalysisResponse.model_validate(parsed_json)
                return validated

        except httpx.TimeoutException:
            logger.warning("Local SLM call timed out after %.1fs. Falling back to degraded mode.", settings.SLM_TIMEOUT_SECONDS)
            return None
        except httpx.ConnectError:
            logger.info("Local SLM not running at %s. Operating in degraded mode.", settings.LOCAL_SLM_URL)
            return None
        except json.JSONDecodeError as jde:
            logger.warning("Local SLM returned invalid JSON: %s. Discarding output.", str(jde))
            return None
        except Exception as exc:
            logger.warning("Local SLM invocation error: %s. Continuing in degraded mode.", str(exc))
            return None
