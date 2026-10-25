"""Is this a real English word? A 45,000-word list (the most frequent lowercase words of a public word-frequency corpus, shipped as
`words_en.txt`, ~380 KB, loaded once on first use, ~1 microsecond per lookup).

Its job is to make typo repair safe: a word that IS in the list ("whether", "play") is never rewritten into something else, so repair can be
aggressive about everything that is not ("paly", "hllo", "wezther"). Names and slang that are not in the list ("karachi", "yaar") may be
considered for repair, but the engine restores whatever the user typed inside an argument afterwards."""
from functools import lru_cache
from pathlib import Path


@lru_cache(maxsize=1)
def words() -> frozenset[str]:
    return frozenset(Path(__file__).with_name("words_en.txt").read_text().split())


def is_word(token: str) -> bool:
    return token.lower() in words()


def distance(a: str, b: str, limit: int) -> int:
    """Damerau-Levenshtein distance (insert, delete, replace, swap two neighbours); returns limit + 1 as soon as it is certain to exceed `limit`."""
    if abs(len(a) - len(b)) > limit:
        return limit + 1
    prev2, prev = None, list(range(len(b) + 1))
    for i in range(1, len(a) + 1):
        cur = [i] + [0] * len(b)
        for j in range(1, len(b) + 1):
            cost = a[i - 1] != b[j - 1]
            cur[j] = min(prev[j] + 1, cur[j - 1] + 1, prev[j - 1] + cost)
            if i > 1 and j > 1 and a[i - 1] == b[j - 2] and a[i - 2] == b[j - 1]:
                cur[j] = min(cur[j], prev2[j - 2] + 1)                     # a transposition ("paly" -> "play") costs one, not two
        if min(cur) > limit:
            return limit + 1
        prev2, prev = prev, cur
    return prev[-1]
