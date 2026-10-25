"""
Indian Numbering System Currency Formatter.

Enforces standard Indian financial comma grouping (crores, lakhs, thousands)
across all autonomous AI email drafts, customer correspondence, account ledger
audits, and notifications (e.g., ₹23,97,500.00 instead of ₹2,397,500.00).
"""

from typing import Union, Optional


def format_inr(
    number: Union[float, int, str, None],
    include_symbol: bool = True,
    decimals: int = 2,
) -> str:
    """
    Format any numeric value into the Indian Numbering System (00,00,00,000).

    Args:
        number: Numeric value to format (float, int, or numeric string).
        include_symbol: If True, prepends the Rupee symbol '₹'.
        decimals: Number of decimal places to include (default: 2).

    Returns:
        Formatted string according to Indian numbering grouping.
        Examples:
            format_inr(2397500) -> "₹23,97,500.00"
            format_inr(10000000) -> "₹1,00,00,000.00"
            format_inr(47500) -> "₹47,500.00"
    """
    if number is None:
        val_str = f"0.{'0' * decimals}" if decimals > 0 else "0"
        return f"₹{val_str}" if include_symbol else val_str

    try:
        num = float(number)
    except (ValueError, TypeError):
        return str(number)

    is_negative = num < 0
    num = abs(num)

    parts = f"{num:.{decimals}f}".split(".")
    int_part = parts[0]
    dec_part = f".{parts[1]}" if decimals > 0 else ""

    if len(int_part) <= 3:
        formatted_int = int_part
    else:
        last_three = int_part[-3:]
        remaining = int_part[:-3]
        grouped = []
        while len(remaining) > 2:
            grouped.insert(0, remaining[-2:])
            remaining = remaining[:-2]
        if remaining:
            grouped.insert(0, remaining)
        formatted_int = ",".join(grouped) + "," + last_three

    result = f"-{formatted_int}{dec_part}" if is_negative else f"{formatted_int}{dec_part}"
    return f"₹{result}" if include_symbol else result
