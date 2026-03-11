from __future__ import annotations

import re
from dataclasses import dataclass
from typing import List, Optional

from .models import (
    CONFIDENCE_HIGH,
    CONFIDENCE_LOW,
    CONFIDENCE_MEDIUM,
    CONFIDENCE_NONE,
)


TOKEN_SPLIT_RE = re.compile(r"[-_]+")
EXPLICIT_TIME_RE = re.compile(r"^t?(?P<hours>\d+)h$", re.IGNORECASE)
T_PREFIX_TIME_RE = re.compile(r"^t(?P<hours>\d+)$", re.IGNORECASE)
PURE_NUMBER_RE = re.compile(r"^\d+$")
BLANK_KEYWORDS = ("blank", "baseline", "base", "reference")


@dataclass
class ParsedName:
    group_key: str = ""
    time_h: Optional[int] = None
    sample_no: str = ""
    confidence: str = CONFIDENCE_NONE
    note: str = ""

    @property
    def ok(self) -> bool:
        return bool(self.group_key and self.time_h is not None and self.sample_no)


def tokenize_stem(stem: str) -> List[str]:
    return [token for token in TOKEN_SPLIT_RE.split(stem.strip()) if token]


def score_blank_candidate(name: str) -> int:
    lowered = name.lower()
    score = 0
    for keyword in BLANK_KEYWORDS:
        if keyword in lowered:
            if keyword == "blank":
                score += 100
            else:
                score += 25
    return score


def is_blank_candidate(name: str) -> bool:
    return score_blank_candidate(name) > 0


def _canonical_group_key(prefix_tokens: List[str], sample_no: str) -> str:
    tokens = [token for token in prefix_tokens if token]
    if sample_no:
        tokens.append(sample_no)
    return "-".join(tokens)


def parse_measurement_name(stem: str) -> ParsedName:
    tokens = tokenize_stem(stem)
    if len(tokens) < 2:
        return ParsedName(note="Not enough tokens to infer group/time/sample.")

    time_idx: Optional[int] = None
    time_h: Optional[int] = None
    time_explicit = False

    for idx, token in enumerate(tokens):
        match = EXPLICIT_TIME_RE.match(token)
        if match:
            time_idx = idx
            time_h = int(match.group("hours"))
            time_explicit = True

    if time_idx is None:
        for idx, token in enumerate(tokens):
            match = T_PREFIX_TIME_RE.match(token)
            if match:
                time_idx = idx
                time_h = int(match.group("hours"))
                time_explicit = True

    sample_idx: Optional[int] = None
    sample_no = ""

    if time_idx is not None:
        for idx in range(len(tokens) - 1, -1, -1):
            if idx == time_idx:
                continue
            if PURE_NUMBER_RE.match(tokens[idx]):
                sample_idx = idx
                sample_no = tokens[idx]
                break

        if sample_idx is None:
            return ParsedName(
                time_h=time_h,
                confidence=CONFIDENCE_LOW,
                note="Time token found but sample number was not inferred.",
            )

        prefix_tokens = [
            token for idx, token in enumerate(tokens) if idx not in {time_idx, sample_idx}
        ]
        if not prefix_tokens:
            return ParsedName(
                time_h=time_h,
                sample_no=sample_no,
                confidence=CONFIDENCE_LOW,
                note="Prefix tokens were not inferred.",
            )

        confidence = CONFIDENCE_HIGH if time_explicit else CONFIDENCE_MEDIUM
        note = "Auto parsed with explicit time token." if time_explicit else "Auto parsed."
        return ParsedName(
            group_key=_canonical_group_key(prefix_tokens, sample_no),
            time_h=time_h,
            sample_no=sample_no,
            confidence=confidence,
            note=note,
        )

    if len(tokens) >= 3 and PURE_NUMBER_RE.match(tokens[-1]) and PURE_NUMBER_RE.match(tokens[-2]):
        sample_no = tokens[-1]
        time_h = int(tokens[-2])
        prefix_tokens = tokens[:-2]
        if prefix_tokens:
            return ParsedName(
                group_key=_canonical_group_key(prefix_tokens, sample_no),
                time_h=time_h,
                sample_no=sample_no,
                confidence=CONFIDENCE_MEDIUM,
                note="Auto parsed from trailing numeric tokens.",
            )

    fallback = re.match(
        r"^(?P<prefix>.+?)[-_]+t?(?P<hours>\d+)h?[-_]+(?P<sample>\d+)$",
        stem,
        re.IGNORECASE,
    )
    if fallback:
        prefix_tokens = tokenize_stem(fallback.group("prefix"))
        sample_no = fallback.group("sample")
        return ParsedName(
            group_key=_canonical_group_key(prefix_tokens, sample_no),
            time_h=int(fallback.group("hours")),
            sample_no=sample_no,
            confidence=CONFIDENCE_MEDIUM,
            note="Parsed with fallback stem pattern.",
        )

    return ParsedName(note="Auto parse failed. Fill in group/time/sample manually.")
