"""Utilities for querying blockchain transaction status.

This module provides helper functions to verify transactions by contacting
blockchain explorer APIs (such as Etherscan). The functions are intentionally
simple so they can be easily mocked in tests and replaced with more robust
implementations in production.
"""

from __future__ import annotations

import logging
from typing import Dict

import requests

logger = logging.getLogger(__name__)

# Basic mapping of network name to a public explorer API endpoint.  The API key
# parameter is included for completeness but left empty so that tests can mock
# out the HTTP request without requiring a real key.
ETHERSCAN_API_URLS: Dict[str, str] = {
    "ethereum": "https://api.etherscan.io/api",
    "goerli": "https://api-goerli.etherscan.io/api",
    "sepolia": "https://api-sepolia.etherscan.io/api",
}


def get_transaction_status(tx_hash: str, network: str = "ethereum") -> str:
    """Return the status of the given transaction hash.

    Parameters
    ----------
    tx_hash:
        Hash of the transaction to look up.
    network:
        Name of the blockchain network (e.g. ``"ethereum"``).

    Returns
    -------
    str
        One of ``"success"``, ``"failed"`` or ``"pending"``.

    Notes
    -----
    The implementation uses the Etherscan style API which returns a JSON object
    with a ``result.status`` field where ``"1"`` means success, ``"0"`` means
    failure and the absence of the field indicates a pending transaction.
    """

    api_url = ETHERSCAN_API_URLS.get(network.lower())
    if not api_url:
        raise ValueError(f"Unsupported network: {network}")

    params = {
        "module": "transaction",
        "action": "gettxreceiptstatus",
        "txhash": tx_hash,
        "apikey": "",  # left blank; tests can mock the request
    }

    try:
        response = requests.get(api_url, params=params, timeout=10)
        response.raise_for_status()
        data = response.json()
        result = data.get("result") or {}
        status = result.get("status")
    except requests.RequestException as exc:  # pragma: no cover - network issues
        logger.error("failed to fetch tx status hash=%s", tx_hash, exc_info=exc)
        raise ValueError("Unable to fetch transaction status") from exc

    if status == "1":
        return "success"
    if status == "0":
        return "failed"
    return "pending"


def verify_transaction(tx_hash: str, network: str = "ethereum") -> bool:
    """Check whether a transaction has been successfully confirmed.

    Returns ``True`` only if the transaction status is ``"success"``.
    Any error raised by :func:`get_transaction_status` will bubble up to the
    caller, allowing service layers to present a clear message to the user.
    """

    return get_transaction_status(tx_hash, network) == "success"
