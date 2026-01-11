"""Console input helpers."""

from __future__ import annotations

import os
import sys
from typing import List

ESCAPE_SENTINEL = "__SAFE_INPUT_ESC__"


def safe_input(prompt: str, default: str = "", allow_escape: bool = False) -> str:
    """Input wrapper that returns default on EOFError and strips whitespace.

    On Windows terminals, when allow_escape=True, supports cancelling with ESC.
    """
    if allow_escape and os.name == "nt" and sys.stdin.isatty() and sys.stdout.isatty():
        try:
            import msvcrt  # type: ignore

            print(prompt, end="", flush=True)
            buffer: List[str] = []
            while True:
                ch = msvcrt.getwch()
                if ch in ("\r", "\n"):
                    print()
                    value = "".join(buffer).strip()
                    return value or default
                if ch == "\x1b":
                    print()
                    return ESCAPE_SENTINEL
                if ch in ("\x08", "\x7f"):
                    if buffer:
                        buffer.pop()
                        print("\b \b", end="", flush=True)
                    continue
                buffer.append(ch)
                print(ch, end="", flush=True)
        except Exception:
            # Fall back to normal input
            pass

    try:
        value = input(prompt).strip()
        if allow_escape and value == "\x1b":
            return ESCAPE_SENTINEL
        return value or default
    except EOFError:
        return default
