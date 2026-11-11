"""weibo-influence-index: a reproducible public-opinion influence index.

Quick start::

    from wii.store import load_cohort
    from wii.score.index import compute_index

    cohort, tables = load_cohort("data/demo")
    result = compute_index(cohort)
    for a in result.ranked():
        print(a.name, a.stars, a.valence)
"""

from .config import INDEX_VERSION  # noqa: F401

__version__ = INDEX_VERSION
__all__ = ["INDEX_VERSION", "__version__"]
