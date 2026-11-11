"""Validation layer: rank recovery, archetype rules, weight sensitivity."""

from .backtest import (  # noqa: F401
    BacktestReport,
    Check,
    kendall_tau,
    load_expectations,
    render_text,
    run_backtest,
    spearman,
    weight_sensitivity,
)
