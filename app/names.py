"""Name normalization shared by the loader and the search."""

from __future__ import annotations

import re
import unicodedata

SUFFIXES = {
    "jr": "jr", "junior": "jr", "sr": "sr", "senior": "sr",
    "ii": "ii", "2nd": "ii", "iii": "iii", "3rd": "iii", "iv": "iv", "4th": "iv", "v": "v",
}
# Honorifics are dropped from the start of a name, credentials from the end.
HONORIFICS = {
    "mr", "mrs", "ms", "miss", "dr", "rev", "reverend", "hon", "honorable", "fr", "father", "sister",
    "msgr", "rabbi", "prof", "the", "very", "rt", "sr",
}
CREDENTIALS = {
    "md", "phd", "dds", "dmd", "do", "jd", "esq", "cpa", "rn", "mba", "lcsw", "edd", "dvm", "pe",
    "cfp", "cfa", "ma", "ms", "msw", "pharmd", "np", "pa", "lpn", "faia", "aia", "cpa", "ret", "usn",
    "usa", "usaf", "facs", "facp", "mph", "bsn", "msn", "dnp", "psyd", "lmft", "lpc", "cae", "cfre",
}
DROP = HONORIFICS | CREDENTIALS
# Credentials that are never also a name; others ("ma", "do") only drop after a comma.
STRONG_CREDENTIALS = CREDENTIALS - {"ma", "ms", "do", "pa", "np", "pe", "usa", "ret"}

_PAREN = re.compile(r"\([^)]*\)|\[[^\]]*\]")
_NONWORD = re.compile(r"[^a-z0-9 ]+")
_SPACE = re.compile(r"\s+")


def _ascii(s: str) -> str:
    return unicodedata.normalize("NFKD", s).encode("ascii", "ignore").decode("ascii")


def normalize_name(raw: str | None) -> str:
    """Lowercase, strip accents and punctuation, drop honorifics, normalize suffixes.

    "SMITH, JOHN A. JR." -> "john a smith jr"; "Dr. María O'Neil, PhD" -> "maria oneil".
    """
    if not raw:
        return ""
    s = _PAREN.sub(" ", _ascii(raw).lower()).replace("'", "").replace("\u2019", "")
    segments = [_NONWORD.sub(" ", seg).split() for seg in s.split(",")]
    segments = [seg for seg in segments if seg]
    if not segments:
        return ""
    suffix = None
    # Comma segments made only of suffixes/credentials ("..., Jr., MD") come off first.
    while len(segments) > 1 and all(t in SUFFIXES or t in DROP for t in segments[-1]):
        for t in segments.pop():
            if t in SUFFIXES and suffix is None:
                suffix = SUFFIXES[t]
    # "Last, First Middle" -> "First Middle Last".
    if len(segments) == 2:
        segments = [segments[1], segments[0]]
    tokens = [t for seg in segments for t in seg]
    while len(tokens) > 2 and tokens[0] in HONORIFICS:
        tokens.pop(0)
    # Unambiguous credentials and suffixes trail the name ("john smith jr md").
    while len(tokens) > 2 and (tokens[-1] in STRONG_CREDENTIALS or tokens[-1] in SUFFIXES):
        t = tokens.pop()
        if t in SUFFIXES and suffix is None:
            suffix = SUFFIXES[t]
    out = []
    for i, t in enumerate(tokens):
        if t in ("jr", "sr", "junior", "senior") and 0 < i:
            suffix = suffix or SUFFIXES[t]
            continue
        out.append(t)
    if suffix:
        out.append(suffix)
    return " ".join(out)


def normalize_org(raw: str | None) -> str:
    if not raw:
        return ""
    s = _ascii(raw).lower().replace("'", "")
    return _SPACE.sub(" ", _NONWORD.sub(" ", s)).strip()


def distinctive(norm: str, generic: frozenset) -> str:
    """An organization name without its generic words ("the smith family foundation" -> "smith"): what tells it
    apart from others. Empty when nothing is left. The generic words come from the data (loader/org_dname.py)."""
    return " ".join(w for w in (norm or "").split() if w not in generic and len(w) > 1)


def name_parts(norm: str) -> tuple[str, str, str, str]:
    """Split a normalized name into (first, middle, last, suffix)."""
    tokens = norm.split()
    suffix = ""
    if tokens and tokens[-1] in ("jr", "sr", "ii", "iii", "iv", "v") and len(tokens) > 1:
        suffix = tokens.pop()
    if not tokens:
        return "", "", "", suffix
    if len(tokens) == 1:
        return tokens[0], "", "", suffix
    return tokens[0], " ".join(tokens[1:-1]), tokens[-1], suffix


def query_tokens(q: str) -> list[str]:
    """Tokens of a search query, normalized the same way as names."""
    return [t for t in _NONWORD.sub(" ", _ascii(q).lower().replace("'", "")).split() if t]
