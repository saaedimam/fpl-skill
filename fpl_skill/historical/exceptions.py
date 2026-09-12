"""Exceptions for the Phase 2 Historical Data Layer and Temporal Firewall."""

class TemporalLeakageError(RuntimeError):
    """Raised when an attempt is made to access data with timestamp > decision cutoff t.
    
    Enforces the mandatory invariant:
    I_t ⊆ D_≤t  AND  I_t ∩ D_>t = ∅
    """
    pass


class ProvenanceError(ValueError):
    """Raised when a datum lacks required provenance metadata (source, observed_at, hash)."""
    pass


class SnapshotIntegrityError(ValueError):
    """Raised when an immutable snapshot's content hash fails verification."""
    pass
