"""Evidence-based dish phrase extraction from Google review content."""

from __future__ import annotations

import re
from collections import Counter
from collections.abc import Iterable


# These cues deliberately favor precision. A phrase is never produced merely
# because it resembles food; it must follow language that identifies a menu
# highlight, order, or recommendation in content returned for the place.
CUE_PATTERNS = (
    re.compile(
        r"\bespecially(?:\s+the)?\s+(.+?)(?=,\s+(?:with|while|along)\b|[.!?]|$)",
        re.IGNORECASE,
    ),
    re.compile(
        r"\b(?:dishes|items|options|offerings)\s+(?:like|including|such as)\s+"
        r"(.+?)(?=,\s+(?:with|while|along)\b|[.!?]|$)",
        re.IGNORECASE,
    ),
    re.compile(
        r"\bincluding\s+(.+?)(?=,\s+(?:with|while|along)\b|[.!?]|$)",
        re.IGNORECASE,
    ),
    re.compile(
        r"\b(?:known for|specializing in|specializes in)\s+"
        r"(.+?)(?=,\s+plus\b|[.!?]|$)",
        re.IGNORECASE,
    ),
)

REVIEW_CUE_PATTERN = re.compile(
    r"\b(?:ordered|order|got|had|tried|try|recommend|recommended|loved|favorite was|"
    r"favorite is)\s+(?:the\s+|a\s+|an\s+|their\s+|our\s+|some\s+)?"
    r"([^.!?;,]{2,70})",
    re.IGNORECASE,
)

LEADING_NOISE = re.compile(
    r"^(?:(?:the|their|our|a|an|some|its)\s+)?"
    r"(?:(?:delicious|fresh|flavorful|popular|signature|excellent|amazing|unique|"
    r"famous|classic|house|homemade|wholesome)\s+)*"
    r"(?:a\s+)?(?:variety\s+of\s+)?",
    re.IGNORECASE,
)

TRAILING_NOISE = re.compile(
    r"\s+(?:was|were|is|are|which|that|because|but)\b.*$",
    re.IGNORECASE,
)

GENERIC_NON_DISHES = {
    "atmosphere",
    "ambiance",
    "customer service",
    "desserts",
    "dishes",
    "excellent service",
    "food",
    "friendly service",
    "generous portion sizes",
    "great service",
    "menu",
    "options",
    "portion sizes",
    "portions",
    "service",
    "staff",
    "takeout",
    "value",
}

PROTECTED_AND_PHRASES = (
    "mac and cheese",
    "fish and chips",
    "biscuits and gravy",
    "peanut butter and jelly",
    "rice and beans",
)

SHARED_DISH_HEADS = (
    "bowls",
    "burgers",
    "burritos",
    "gyros",
    "pastas",
    "pizzas",
    "plates",
    "platters",
    "sandwiches",
    "tacos",
    "wings",
)


def _split_list(phrase: str) -> list[str]:
    # Expand phrases such as "chicken and lamb platters" before normal list
    # splitting so neither protein is reduced to the vague dish "chicken".
    shared_head = re.fullmatch(
        rf"\s*([\w' -]+?)\s+and\s+([\w' -]+?)\s+({'|'.join(SHARED_DISH_HEADS)})\s*",
        phrase,
        flags=re.IGNORECASE,
    )
    if shared_head:
        first, second, head = shared_head.groups()
        return [f"{first} {head}", f"{second} {head}"]

    protected = phrase
    replacements: dict[str, str] = {}
    for index, item in enumerate(PROTECTED_AND_PHRASES):
        token = f"__protected_{index}__"
        replacements[token] = item
        protected = re.sub(re.escape(item), token, protected, flags=re.IGNORECASE)

    protected = re.sub(r",\s*(?:and|or)\s+", ", ", protected, flags=re.IGNORECASE)
    parts = re.split(r"\s*,\s*|\s+(?:and|or)\s+", protected, flags=re.IGNORECASE)
    return [
        next((value for token, value in replacements.items() if token in part), part)
        for part in parts
    ]


def _clean_candidate(candidate: str) -> str | None:
    value = re.sub(r"\s+", " ", candidate).strip(" -–—,:;.!?\"'()")
    value = LEADING_NOISE.sub("", value)
    value = TRAILING_NOISE.sub("", value).strip(" -–—,:;.!?\"'()")
    normalized = value.casefold()

    if (
        not normalized
        or normalized in GENERIC_NON_DISHES
        or len(normalized) < 3
        or len(normalized.split()) > 6
        or any(
            noise in normalized
            for noise in ("service", "staff", "atmosphere", "ambiance", "portion size")
        )
    ):
        return None
    return value


def extract_recommended_dishes(
    review_summary: str,
    generative_summary: str,
    review_texts: Iterable[str],
    *,
    limit: int = 3,
) -> tuple[str, ...]:
    """Extract up to ``limit`` directly evidenced menu phrases.

    Review-summary mentions receive the highest weight because Google has already
    synthesized them across reviews. Raw review cues provide a conservative
    fallback when summaries are missing.
    """

    scores: Counter[str] = Counter()
    display_names: dict[str, str] = {}

    def add_phrase(phrase: str, weight: int) -> None:
        for part in _split_list(phrase):
            cleaned = _clean_candidate(part)
            if not cleaned:
                continue
            key = cleaned.casefold()
            scores[key] += weight
            display_names.setdefault(key, cleaned)

    # Prefer the review summary: it synthesizes themes across reviewers and is
    # therefore stronger evidence than one recent review or a broad overview.
    for pattern in CUE_PATTERNS:
        for match in pattern.finditer(review_summary):
            add_phrase(match.group(1), 4)

    if not scores:
        for pattern in CUE_PATTERNS:
            for match in pattern.finditer(generative_summary):
                add_phrase(match.group(1), 2)

    if not scores:
        for review in review_texts:
            for match in REVIEW_CUE_PATTERN.finditer(review):
                add_phrase(match.group(1), 1)

    ranked = sorted(scores, key=lambda key: (-scores[key], key))
    return tuple(display_names[key] for key in ranked[:limit])
