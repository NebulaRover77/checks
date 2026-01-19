# cli_utils.py
from __future__ import annotations
import re
from typing import Optional, Callable

def prompt(msg: str, default: Optional[str] = None) -> str:
    sfx = f" [{default}]" if default is not None else ""
    val = input(f"{msg}{sfx}: ").strip()
    return default if val == "" and default is not None else val

def prompt_required(
    msg: str,
    default: Optional[str] = None,
    validator: Optional[Callable[[str], bool]] = None,
    err: str = "Invalid value",
) -> str:
    while True:
        val = prompt(msg, default)
        if val == "" and default is None:
            print("Value is required.")
            continue
        if validator and val and not validator(val):
            print(err)
            continue
        return val

def prompt_yes_no(msg: str, default: bool = True) -> bool:
    sfx = " [Y/n]" if default else " [y/N]"
    while True:
        val = input(f"{msg}{sfx}: ").strip().lower()
        if val == "" and default is not None:
            return default
        if val in ("y", "yes"): return True
        if val in ("n", "no"):  return False
        print("Please answer y or n.")

def prompt_int(
    msg: str,
    default: Optional[int] = None,
    *,
    min: Optional[int] = None,
    max: Optional[int] = None,
) -> int:
    while True:
        raw = prompt(msg, str(default) if default is not None else None)
        try:
            val = int(raw)
        except (TypeError, ValueError):
            print("Please enter a valid integer.")
            continue
        if min is not None and val < min:
            print(f"Value must be ≥ {min}.")
            continue
        if max is not None and val > max:
            print(f"Value must be ≤ {max}.")
            continue
        return val

def prompt_float(
    msg: str,
    default: Optional[float] = None,
    *,
    min: Optional[float] = None,
    max: Optional[float] = None,
) -> float:
    while True:
        raw = prompt(msg, f"{default}" if default is not None else None)
        try:
            val = float(raw)
        except (TypeError, ValueError):
            print("Please enter a valid number.")
            continue
        if min is not None and val < min:
            print(f"Value must be ≥ {min}.")
            continue
        if max is not None and val > max:
            print(f"Value must be ≤ {max}.")
            continue
        return val

def is_routing(v: str) -> bool:
    return bool(re.fullmatch(r"\d{9}", v))

def prompt_page_size() -> tuple[float, float]:
    """
    Returns (width_in, height_in).
    1) 8.5 × 4.0   (one check)
    2) 8.5 × 7.5   (two checks)
    3) 8.5 × 11.0  (three checks)
    4) Other
    """
    print("\nPage sizes:")
    print("  1) 8.5 × 4.0   (one check)")
    print("  2) 8.5 × 7.5   (two checks)")
    print("  3) 8.5 × 11.0  (three checks)")
    print("  4) Other")

    choice = prompt_required("Select page size [1-4]", default="3",
                             validator=lambda s: s in {"1","2","3","4"})
    if choice == "1":
        return (8.5, 4.0)
    if choice == "2":
        return (8.5, 7.5)
    if choice == "3":
        return (8.5, 11.0)

    # Other/custom in inches
    w = prompt_float("Enter page width (inches)", default=8.5, min=1.0)
    h = prompt_float("Enter page height (inches)", default=11.0, min=1.0)
    return (w, h)

    choice = prompt_required("Select page size [1-4]", default="1",
                             validator=lambda s: s in {"1","2","3","4"})
    if choice == "1":
        return (8.5, 11.0)
    if choice == "2":
        return (8.5, 14.0)
    if choice == "3":
        return (8.27, 11.69)

    # Other/custom in inches
    w = prompt_float("Enter page width (inches)", default=8.5, min=1.0)
    h = prompt_float("Enter page height (inches)", default=11.0, min=1.0)
    return (w, h)
