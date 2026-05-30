"""Thin orchestration wrapper around the repository's SharedContext.

This re-exports the existing SharedContext implementation so orchestration
components import from a stable location without duplicating state.
"""
from shared_context import SharedContext


def get_context() -> SharedContext:
    # callers should create a single SharedContext and pass it around; this
    # convenience returns a new instance for lightweight use.
    return SharedContext()
