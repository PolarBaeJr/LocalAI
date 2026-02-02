"""
Optional debug overrides.
- Set ENABLE_DEBUG_SETTINGS = True (or call Debug.enable_debug_settings()) to activate.
- FORCE_MODEL can be:
    None            -> no override; normal selection applies
    "local"         -> force the local model (deepseek-r1:14b)
    "cloud"         -> force the cloud model (deepseek-v3.2:cloud)
    "<model tag>"   -> force a specific model string
"""

ENABLE_DEBUG_SETTINGS = False
FORCE_MODEL: str | None = None
