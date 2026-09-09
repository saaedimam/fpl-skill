"""fpl-skill v2 observation layer: live elite-manager monitoring.

Additive package over the frozen v1.1.0 engine. Uses only public,
official FPL API. No authentication, no private endpoints.
"""
from .model import SCHEMA_VERSION as SCHEMA_VERSION  # noqa: F401
__all__ = ["SCHEMA_VERSION"]
