"""Explicit old immediate-sync hypothesis for retained overflow diagnostics.

This is not the measured overflow activation/spacing behavior. Keep it opt-in
so an experimental complete-program gate cannot be mistaken for supported
functional execution. Original hardware counterexamples remain unchanged.
"""
from contextlib import contextmanager
import hashlib
import os
from pathlib import Path

SOURCE_SHA256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest()


@contextmanager
def counter_sync_hypothesis():
    key='AGX_EXPERIMENTAL_EXEC_OVERFLOW';old=os.environ.get(key)
    os.environ[key]='counter-sync'
    try:yield
    finally:
        if old is None:os.environ.pop(key,None)
        else:os.environ[key]=old
