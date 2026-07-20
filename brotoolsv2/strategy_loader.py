"""
brotoolsv2.strategy_loader

Discovers and loads all Strategy classes found in brotoolsv2/strategies/.
Only strategies with active = True are loaded into the running session.
The active flag is read once at startup and is not toggled at runtime.
"""
