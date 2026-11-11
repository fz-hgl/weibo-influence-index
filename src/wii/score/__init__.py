"""Scoring: factors -> normalisation -> magnitude -> stars."""

from .index import ArtistScore, IndexResult, compute_index, stars_from_magnitude  # noqa: F401
from .explain import explain_artist, explain_index, render_text  # noqa: F401
