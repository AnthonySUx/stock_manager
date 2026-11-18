"""Text matching: case-insensitive "contains" filters for keyword search
(#49), and dish title matching for Explore (#66 part 6).

A keyword is matched literally: `%` and `_` are ordinary characters, not
LIKE wildcards, so searching "50%" does not match every title with "50".
"""
import re
from dataclasses import dataclass
from typing import Iterable, Optional

from sqlalchemy import func

# "/" instead of the usual backslash: backslashes need extra quoting in
# MySQL string literals, "/" behaves the same on MySQL and SQLite.
_ESCAPE = "/"


def escape_like(text: str) -> str:
    """Escape LIKE wildcards (and the escape character itself) in `text`."""
    return (
        text.replace(_ESCAPE, _ESCAPE * 2)
        .replace("%", _ESCAPE + "%")
        .replace("_", _ESCAPE + "_")
    )


def contains_ci(column, keyword: str):
    """SQL condition: lower(column) contains lower(keyword), literally."""
    return func.lower(column).like(f"%{escape_like(keyword.lower())}%", escape=_ESCAPE)


# ─── Dish title matching (#66 part 6) ────────────────────────────

_CJK_WORD = re.compile(r"^[一-鿿]+$")
_BRACKETS = re.compile(r"[（(【\[][^）)】\]]*[）)】\]]")
_NOT_WORD = re.compile(r"[\W_]+")
_HOWTOCOOK_SUFFIX = "的做法"

# Fuzzy thresholds, tuned on the 373 HowToCook titles: below them, pairs
# such as 青椒炒肉 / 辣椒炒肉 or 黄瓜炒蛋 / 黄瓜炒肉 would be linked.
SIMILAR_DICE = 0.8
CONTAINED_DICE = 0.5
CONTAINED_MIN_LENGTH = 3


@dataclass(frozen=True)
class TitleMatch:
    recipe_id: int
    title: str
    score: float  # 1.0 for an exact match after normalization


def _bigrams(text: str) -> set[str]:
    return {text[i:i + 2] for i in range(len(text) - 1)} or {text}


def dice(a: str, b: str) -> float:
    """Character-bigram Dice coefficient (0..1)."""
    x, y = _bigrams(a), _bigrams(b)
    return 2 * len(x & y) / (len(x) + len(y))


class TitleMatcher:
    """Find the local recipe a dish title refers to.

    Titles are normalized first: the HowToCook suffix "的做法", bracketed
    notes, punctuation and spaces are removed, and Chinese ingredient
    synonyms are mapped to one name (西红柿 → 番茄, 鸡蛋 → 蛋), so 番茄炒蛋
    and 西红柿炒鸡蛋 are the same dish. A title then matches when it is:
    1. equal to a recipe title;
    2. very similar (bigram Dice >= SIMILAR_DICE), e.g. 番茄豆腐汤 / 西红柿豆腐汤羹;
    3. contained in it or containing it, the shorter one at least
       CONTAINED_MIN_LENGTH Chinese characters and Dice >= CONTAINED_DICE,
       e.g. 红烧肉 / 简易红烧肉, 黄焖鸡米饭 / 黄焖鸡. Not for Latin text, where
       a few letters say little ("tomato egg" / "tomato egg fried rice").
    The best score wins; on a tie, the older recipe (lower id).
    """

    def __init__(self, recipes: Iterable[tuple[int, str]], synonyms: dict[str, list[str]]):
        pairs = [
            (alias, canonical)
            for canonical, aliases in synonyms.items() if _CJK_WORD.match(canonical)
            for alias in aliases if _CJK_WORD.match(alias) and len(alias) >= 2 and alias != canonical
        ]
        pairs.append(("鸡蛋", "蛋"))
        self._pairs = sorted(pairs, key=lambda p: -len(p[0]))  # 鸡胸肉 before 鸡肉
        self._recipes = []
        for recipe_id, title in recipes:
            key = self.normalize(title or "")
            if key:
                self._recipes.append((key, recipe_id, title))

    def normalize(self, title: str) -> str:
        text = title.strip().lower()
        if text.endswith(_HOWTOCOOK_SUFFIX):
            text = text[: -len(_HOWTOCOOK_SUFFIX)]
        text = _NOT_WORD.sub("", _BRACKETS.sub("", text))
        for alias, canonical in self._pairs:
            text = text.replace(alias, canonical)
        return text

    @staticmethod
    def _score(key: str, other: str) -> float:
        score = dice(key, other)  # 1.0 for equal titles
        if score >= SIMILAR_DICE:
            return score
        shorter, longer = sorted((key, other), key=len)
        if (len(shorter) >= CONTAINED_MIN_LENGTH and _CJK_WORD.match(shorter)
                and shorter in longer and score >= CONTAINED_DICE):
            return score
        return 0.0

    def match(self, title: Optional[str]) -> Optional[TitleMatch]:
        key = self.normalize(title or "")
        if not key:
            return None
        best = None
        for other, recipe_id, recipe_title in self._recipes:
            score = self._score(key, other)
            if score <= 0:
                continue
            rank = (-score, recipe_id)
            if best is None or rank < best[0]:
                best = (rank, TitleMatch(recipe_id, recipe_title, score))
        return best[1] if best else None
