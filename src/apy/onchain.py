"""On-chain data fetch utilities using The Graph for Curve pools."""

from __future__ import annotations

from typing import Dict, List

import requests

# Public The Graph endpoint for Curve Finance mainnet pools
THEGRAPH_CURVE_ENDPOINT = "https://api.thegraph.com/subgraphs/name/curvefi/curve"


def fetch_onchain_pool_data() -> List[Dict[str, float]]:
    """Fetch pool metrics from The Graph.

    Returns a list of dictionaries containing ``pool_id``, ``apy``, ``bribe``,
    ``trading_fee`` and ``crv_reward`` similar to :func:`curve.fetch_pool_data`.
    ``apy`` represents the sum of all reward APYs and ``bribe`` represents the
    APY contributed by non-CRV rewards.
    """

    query = (
        "{\n"
        "  pools(first: 1000) {\n"
        "    id\n"
        "    swapFee\n"
        "    gauge {\n"
        "      rewardData {\n"
        "        apy\n"
        "        token { symbol }\n"
        "      }\n"
        "    }\n"
        "  }\n"
        "}"
    )

    try:
        response = requests.post(
            THEGRAPH_CURVE_ENDPOINT,
            json={"query": query},
            timeout=10,
        )
        response.raise_for_status()
        data = response.json().get("data", {}).get("pools", [])
    except Exception as exc:  # pragma: no cover - network failure
        raise RuntimeError("failed to fetch on-chain data") from exc

    pools: List[Dict[str, float]] = []
    for pool in data:
        pool_id = pool.get("id")
        trading_fee = float(pool.get("swapFee") or pool.get("fee") or 0.0)
        reward_data = ((pool.get("gauge") or {}).get("rewardData") or [])

        total_apy = 0.0
        bribe = 0.0
        crv_reward = 0.0
        for reward in reward_data:
            apy = float(reward.get("apy") or 0.0)
            total_apy += apy
            token_symbol = ((reward.get("token") or {}).get("symbol") or "").lower()
            if token_symbol == "crv":
                crv_reward = apy
            else:
                bribe += apy

        pools.append(
            {
                "pool_id": pool_id,
                "apy": total_apy,
                "bribe": bribe,
                "trading_fee": trading_fee,
                "crv_reward": crv_reward,
            }
        )

    return pools
