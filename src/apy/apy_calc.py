from typing import Iterable


def calculate_compound_apy(returns: Iterable[float]) -> float:
    """Calculate compounded APY from a series of periodic returns.

    Parameters
    ----------
    returns: Iterable[float]
        Sequence of periodic percentage returns (e.g. daily APY values).

    Returns
    -------
    float
        The compounded APY expressed as a percentage. Returns ``0.0`` when
        the input sequence is empty.
    """
    total = 1.0
    has_data = False
    for r in returns:
        if r is None:
            continue
        has_data = True
        total *= 1 + r / 100
    if not has_data:
        return 0.0
    return (total - 1) * 100
