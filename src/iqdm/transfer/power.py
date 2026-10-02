"""Keep Windows from sleeping while a transfer runs (SPEC section 8, "Copy engine").

keep_awake() calls SetThreadExecutionState on the thread that runs the transfer. The
request ends when the context exits, and also when that thread ends. The display may
still turn off. Off Windows it does nothing.
"""

import sys
from collections.abc import Callable, Iterator
from contextlib import contextmanager

ES_CONTINUOUS = 0x80000000
ES_SYSTEM_REQUIRED = 0x00000001

StateSetter = Callable[[int], int]


def _windows_setter() -> StateSetter | None:
    if sys.platform != "win32":
        return None
    import ctypes

    func = ctypes.windll.kernel32.SetThreadExecutionState
    func.argtypes = [ctypes.c_uint32]
    func.restype = ctypes.c_uint32
    return func


@contextmanager
def keep_awake(set_state: StateSetter | None = None) -> Iterator[None]:
    """Ask Windows to stay awake until the block ends. set_state is for tests."""
    setter = _windows_setter() if set_state is None else set_state
    if setter is None:
        yield
        return
    setter(ES_CONTINUOUS | ES_SYSTEM_REQUIRED)
    try:
        yield
    finally:
        setter(ES_CONTINUOUS)
