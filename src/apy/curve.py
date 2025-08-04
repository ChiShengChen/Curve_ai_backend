"""Client helpers for retrieving Curve pool data."""

from typing import List, Dict
import requests

CURVE_API = "https://api.curve.fi/api/getPools/ethereum/main"


def fetch_pool_data() -> List[Dict[str, float]]:
    """Fetch pool metrics from the Curve API.

    The structure of the Curve API may change; this function attempts to extract
    common fields such as APY, bribe rewards, trading fee and CRV rewards.
    Missing fields are filled with ``0``.
    """
    try:
        response = requests.get(CURVE_API, timeout=10)
        response.raise_for_status()
        data = response.json().get("data", {}).get("poolData", [])
    except Exception:
        # In case of network or parsing errors return empty result to avoid
        # crashing the scheduler.
        return []

    pools: List[Dict[str, float]] = []
    for pool in data:
        pool_id = pool.get("id") or pool.get("address")
        apy = 0.0
        apy_data = pool.get("apy") or pool.get("apyFormatted")
        if isinstance(apy_data, dict):
            apy = apy_data.get("total") or apy_data.get("apy", 0.0)
        elif isinstance(apy_data, (int, float)):
            apy = float(apy_data)
        bribe = pool.get("bribeApy") or 0.0
        trading_fee = pool.get("tradingFee") or pool.get("fee") or 0.0
        crv = 0.0
        for reward in pool.get("gaugeRewards", []) or []:
            token = reward.get("token", "").lower()
            if token == "crv":
                crv = reward.get("apy", 0.0)
                break
        pools.append(
            {
                "pool_id": pool_id,
                "apy": apy,
                "bribe": bribe,
                "trading_fee": trading_fee,
                "crv": crv,
            }
        )
    return pools
