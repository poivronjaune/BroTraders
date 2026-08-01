"""
brotoolsv2.strategy_loader

Discovers and loads all Strategy classes found in brotoolsv2/strategies/.
Only strategies with active = True are loaded into the running session.
The active flag is read once at startup and is not toggled at runtime.

Per-file failures (missing Strategy class, missing 'active' attribute,
or an exception during instantiation) are logged as warnings and skipped
so one broken strategy file does not by itself take down the whole
loader. However, if zero valid active strategies are found after
scanning every file, load_active_strategies() raises - a session with
no strategies to run is not a valid state to start trading in.
"""

import importlib
import logging
import pkgutil

import brotoolsv2.strategies as strategies_package

logger = logging.getLogger(__name__)


def discover_strategy_module_names() -> list[str]:
    """
    Returns the list of module names found in brotoolsv2/strategies/,
    excluding __init__. Does not import anything yet.
    """
    return [
        module_info.name
        for module_info in pkgutil.iter_modules(strategies_package.__path__)
    ]


def load_active_strategies() -> list:
    """
    Imports every module in brotoolsv2/strategies/, instantiates its
    Strategy class, and returns instances where active is True.

    Raises RuntimeError if no active strategies are found after scanning
    every file - a session cannot start with nothing to trade.
    """
    module_names = discover_strategy_module_names()
    active_strategies = []

    for module_name in module_names:
        full_module_name = f"brotoolsv2.strategies.{module_name}"

        try:
            module = importlib.import_module(full_module_name)
        except Exception as e:
            logger.warning(f"⚠️  Could not import {full_module_name}: {type(e).__name__}: {e}")
            continue

        strategy_class = getattr(module, "Strategy", None)
        if strategy_class is None:
            logger.warning(f"⚠️  {full_module_name} has no 'Strategy' class - skipped.")
            continue

        try:
            instance = strategy_class()
        except Exception as e:
            logger.warning(f"⚠️  {full_module_name}.Strategy() failed to instantiate: {type(e).__name__}: {e}")
            continue

        if not hasattr(instance, "active"):
            logger.warning(f"⚠️  {full_module_name}.Strategy has no 'active' attribute - skipped.")
            continue

        if instance.active:
            logger.info(f"✅ Loaded strategy: {instance.name}")
            active_strategies.append(instance)
        else:
            logger.info(f"⏸️  Strategy inactive, not loaded: {instance.name}")

    if not active_strategies:
        raise RuntimeError(
            "❌ No active strategies found in brotoolsv2/strategies/. "
            "At least one strategy must have active = True to start a session."
        )

    return active_strategies