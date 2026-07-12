"""Language detection with graceful degradation.

Uses ``langdetect`` when installed (the ``[multilingual]`` extra). Without it,
falls back to a Unicode-script heuristic that distinguishes Cyrillic (ru) and
CJK (zh) from Latin scripts, defaulting the rest to English.
"""

from typing import Tuple

SUPPORTED = {"en", "ru", "zh", "de"}
LANGUAGE_NAMES = {"en": "English", "ru": "Russian", "zh": "Chinese", "de": "German"}

_LANGDETECT_MAP = {"en": "en", "ru": "ru", "zh-cn": "zh", "zh-tw": "zh", "de": "de"}

try:  # optional dependency
    from langdetect import LangDetectException, detect_langs

    _HAS_LANGDETECT = True
except Exception:  # pragma: no cover - exercised only without the extra
    _HAS_LANGDETECT = False


def _script_heuristic(text: str) -> Tuple[str, float]:
    cyrillic = cjk = latin = 0
    for ch in text:
        o = ord(ch)
        if 0x0400 <= o <= 0x04FF:
            cyrillic += 1
        elif 0x4E00 <= o <= 0x9FFF or 0x3040 <= o <= 0x30FF:
            cjk += 1
        elif ch.isalpha():
            latin += 1
    total = cyrillic + cjk + latin
    if total == 0:
        return "en", 0.3
    if cjk / total > 0.2:
        return "zh", round(cjk / total, 4)
    if cyrillic / total > 0.2:
        return "ru", round(cyrillic / total, 4)
    return "en", 0.5


def detect_language(text: str) -> Tuple[str, float]:
    """Return ``(language_code, confidence)`` for ``text``.

    Supported codes: en, ru, zh, de. Unsupported detections fall back to en.
    """
    if not text or len(text.strip()) < 10:
        return "en", 0.3

    if _HAS_LANGDETECT:
        try:
            for result in detect_langs(text[:500]):
                mapped = _LANGDETECT_MAP.get(result.lang)
                if mapped:
                    return mapped, round(result.prob, 4)
            return "en", 0.3
        except LangDetectException:
            return "en", 0.3

    return _script_heuristic(text)


def language_info(text: str) -> dict:
    code, confidence = detect_language(text)
    return {
        "code": code,
        "name": LANGUAGE_NAMES.get(code, "Unknown"),
        "confidence": confidence,
        "supported": code in SUPPORTED,
    }
