"""Cross-venue market clustering + best-price computation.

Public surface is one function:  cluster(markets) -> list[UnifiedMarket]

The current implementation is a deliberately SIMPLE fuzzy-title matcher: difflib
ratio over normalized questions, GUARDED by a distinctive-token check so that
templated markets ("Will <X> win the 2026 FIFA World Cup?") don't collapse all
their different subjects into one cluster. Pure difflib over-merges here because
the shared boilerplate dominates the character ratio; we additionally require the
rare/distinctive tokens (the entity names — e.g. "lebron james") to overlap. It
is isolated behind the `Matcher` protocol so a stronger implementation can drop
in without touching callers:

    # TODO(semantic-matching): implement EmbeddingMatcher(Matcher) that
    #   1. embeds normalized questions (numpy is already a dependency),
    #   2. clusters by cosine similarity (e.g. threshold or HDBSCAN),
    #   3. LLM-verifies borderline pairs as the same underlying event.
    # Then set DEFAULT_MATCHER = EmbeddingMatcher(); nothing else changes.

Inverted framing (one venue's YES == another's NO) is normalized BEFORE prices
are compared, via a negation-parity heuristic relative to the cluster anchor.
"""

from __future__ import annotations

import re
from collections import Counter
from difflib import SequenceMatcher
from typing import Protocol

from app.config import settings
from app.models import CanonicalMarket, PriceQuote, UnifiedMarket

# ----------------------------------------------------------------------------
# Question normalization
# ----------------------------------------------------------------------------

_MONTHS = (
    "january february march april may june july august september october "
    "november december jan feb mar apr jun jul aug sep sept oct nov dec"
).split()
_WEEKDAYS = "monday tuesday wednesday thursday friday saturday sunday".split()
_FILLER = {
    "will", "the", "a", "an", "to", "of", "be", "by", "in", "on", "at", "for",
    "is", "are", "this", "that", "than", "and", "or", "do", "does", "did",
    "before", "after", "during", "between",
}
_STRIP_TOKENS = set(_MONTHS) | set(_WEEKDAYS) | _FILLER
_YEAR_RE = re.compile(r"\b(19|20)\d{2}\b")
_ORDINAL_RE = re.compile(r"\b\d{1,2}(st|nd|rd|th)\b")
_NON_ALNUM = re.compile(r"[^a-z0-9\s]+")
_WS = re.compile(r"\s+")

_NEGATION_TOKENS = {"no", "not", "never", "fail", "fails", "without", "miss", "lose", "loses"}


def normalize_question(question: str) -> str:
    """Lowercase, strip punctuation/dates/filler, collapse whitespace."""
    text = question.lower()
    text = _YEAR_RE.sub(" ", text)
    text = _ORDINAL_RE.sub(" ", text)
    text = _NON_ALNUM.sub(" ", text)
    tokens = [t for t in text.split() if t not in _STRIP_TOKENS]
    return _WS.sub(" ", " ".join(tokens)).strip()


def _negation_parity(question: str) -> int:
    """0 if affirmative framing, 1 if negated framing (odd # of negations)."""
    tokens = re.sub(r"[^a-z\s]+", " ", question.lower()).split()
    negations = sum(1 for t in tokens if t in _NEGATION_TOKENS)
    return negations % 2


# ----------------------------------------------------------------------------
# Matcher interface
# ----------------------------------------------------------------------------


class Matcher(Protocol):
    def cluster(self, markets: list[CanonicalMarket]) -> list[UnifiedMarket]:
        ...


class DifflibMatcher:
    """Greedy fuzzy-title clustering: difflib ratio + distinctive-token guard.

    The guard that stops templated markets from over-merging works on the
    SYMMETRIC DIFFERENCE of two questions' tokens. When two near-identical
    questions differ, the differing tokens are either shared-template words
    ("win", "nomination") or the thing that actually distinguishes the markets
    (an entity name or number: "usa" vs "brazil", "30" vs "50"). We flag a token
    as a real discriminator when it is globally RARE (low document frequency).
    If the symmetric difference contains any rare discriminator, the two markets
    are different and must not merge — independent of how big the template family
    is (FIFA, NFL, and nominee templates all differ in size, so a single global
    df cutoff over "distinctive" tokens cannot separate them; symdiff can).
    """

    def __init__(
        self,
        threshold: float | None = None,
        significant_df_ratio: float = 0.05,
    ) -> None:
        self.threshold = threshold if threshold is not None else settings.match_threshold
        self.significant_df_ratio = significant_df_ratio

    def cluster(self, markets: list[CanonicalMarket]) -> list[UnifiedMarket]:
        if not markets:
            return []

        norm: dict[str, str] = {m.id: normalize_question(m.question) for m in markets}
        tokens: dict[str, frozenset[str]] = {
            mid: frozenset(text.split()) for mid, text in norm.items()
        }
        significant = self._significant_tokens(tokens)

        # High-volume anchors first → representative phrasing is the liquid one.
        ordered = sorted(markets, key=lambda m: m.volume, reverse=True)
        used: set[str] = set()
        clusters: list[UnifiedMarket] = []

        for anchor in ordered:
            if anchor.id in used:
                continue
            used.add(anchor.id)
            a_norm = norm[anchor.id]
            a_tok = tokens[anchor.id]

            members: list[CanonicalMarket] = [anchor]
            ratios: dict[str, float] = {anchor.id: 1.0}

            matcher = SequenceMatcher(autojunk=False)
            matcher.set_seq1(a_norm)
            for cand in ordered:
                if cand.id in used:
                    continue
                c_norm = norm[cand.id]
                if not a_norm or not c_norm:
                    continue
                if not self._subject_match(a_tok, tokens[cand.id], significant):
                    continue
                matcher.set_seq2(c_norm)
                # Cheap upper-bound gates before the O(n*m) ratio().
                if matcher.real_quick_ratio() < self.threshold:
                    continue
                if matcher.quick_ratio() < self.threshold:
                    continue
                ratio = matcher.ratio()
                if ratio >= self.threshold:
                    used.add(cand.id)
                    members.append(cand)
                    ratios[cand.id] = ratio

            clusters.append(self._build_unified(anchor, members, ratios))

        return clusters

    def _significant_tokens(self, tokens: dict[str, frozenset[str]]) -> frozenset[str]:
        """Globally rare tokens — entity names / numbers that discriminate markets."""
        df: Counter[str] = Counter()
        for toks in tokens.values():
            df.update(toks)
        cutoff = max(3, int(len(tokens) * self.significant_df_ratio))
        return frozenset(t for t, count in df.items() if count <= cutoff)

    @staticmethod
    def _subject_match(
        a: frozenset[str], b: frozenset[str], significant: frozenset[str]
    ) -> bool:
        """Reject if the tokens that differ include a rare discriminator."""
        return not ((a ^ b) & significant)

    def _build_unified(
        self,
        anchor: CanonicalMarket,
        members: list[CanonicalMarket],
        ratios: dict[str, float],
    ) -> UnifiedMarket:
        anchor_parity = _negation_parity(anchor.question)

        best_yes: PriceQuote | None = None
        best_no: PriceQuote | None = None

        for m in members:
            # Orient member prices into the anchor's framing before comparing.
            flip = _negation_parity(m.question) != anchor_parity
            yes_p = m.no_price if flip else m.yes_price
            no_p = m.yes_price if flip else m.no_price

            if best_yes is None or yes_p < best_yes.price:
                best_yes = PriceQuote(venue=m.venue, price=yes_p, market_id=m.id)
            if best_no is None or no_p < best_no.price:
                best_no = PriceQuote(venue=m.venue, price=no_p, market_id=m.id)

        confidence = 1.0 if len(members) == 1 else min(ratios.values())
        venues = sorted({m.venue for m in members})

        return UnifiedMarket(
            id=f"u:{anchor.id}",
            canonical_question=anchor.question,
            members=[m.id for m in members],
            best_yes=best_yes,
            best_no=best_no,
            match_confidence=round(confidence, 4),
            category=anchor.category,
            country=anchor.country,
            theme=anchor.theme,
            venues=venues,
        )


# Swap this for a stronger Matcher (see module docstring TODO) — callers use
# the module-level `cluster` and never see the implementation.
DEFAULT_MATCHER: Matcher = DifflibMatcher()


def cluster(markets: list[CanonicalMarket]) -> list[UnifiedMarket]:
    """Group duplicate markets across venues and compute best price per side."""
    return DEFAULT_MATCHER.cluster(markets)
