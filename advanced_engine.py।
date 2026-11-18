
#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
ADVANCED CRYPTO INTELLIGENCE ENGINE
Version: 1.0.0

Output:
data/advanced_data.json

Sources:
- Binance Spot public API
- Binance USD-M Futures public API

Missing ETF and on-chain data are explicitly marked unavailable.
No synthetic values are generated.
"""

import json
import math
from datetime import datetime, timezone
from pathlib import Path
from urllib.request import Request, urlopen


BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / "data"
OUTPUT_FILE = DATA_DIR / "advanced_data.json"

TIMEOUT = 15
USER_AGENT = "CryptoMacroDashboard-Advanced/1.0"


def utc_now():
    return (
        datetime.now(timezone.utc)
        .replace(microsecond=0)
        .isoformat()
        .replace("+00:00", "Z")
    )


def fetch_json(url):
    request = Request(
        url,
        headers={"User-Agent": USER_AGENT}
    )

    with urlopen(request, timeout=TIMEOUT) as response:
        return json.loads(response.read().decode("utf-8"))


def unavailable(reason):
    return {
        "value": None,
        "status": "UNAVAILABLE",
        "reason": reason
    }


def metric(value, unit, source):
    try:
        value = float(value)

        if not math.isfinite(value):
            raise ValueError("Non-finite value")

        return {
            "value": value,
            "unit": unit,
            "status": "OK",
            "source": source,
            "fetched_at": utc_now()
        }

    except (TypeError, ValueError):
        return unavailable("Valid numeric data unavailable")


def safe_fetch(url):
    try:
        return fetch_json(url), None
    except Exception as error:
        return None, str(error)[:250]


def get_derivatives(symbol):
    base = "https://fapi.binance.com"
    result = {"symbol": symbol}

    # Funding, mark price and index price
    data, error = safe_fetch(
        f"{base}/fapi/v1/premiumIndex?symbol={symbol}"
    )

    if data:
        result["mark_price"] = metric(
            data.get("markPrice"),
            "USDT",
            "Binance USD-M Futures"
        )

        result["index_price"] = metric(
            data.get("indexPrice"),
            "USDT",
            "Binance USD-M Futures"
        )

        result["last_funding_rate"] = metric(
            float(data.get("lastFundingRate", 0)) * 100,
            "% per 8h",
            "Binance USD-M Futures"
        )

        mark = float(data.get("markPrice", 0))
        index = float(data.get("indexPrice", 0))

        basis = ((mark / index) - 1) * 100 if index else None

        result["basis_percent"] = metric(
            basis,
            "%",
            "Binance USD-M Futures"
        )

        result["next_funding_time"] = data.get(
            "nextFundingTime"
        )

    else:
        reason = "Binance Futures API unavailable: " + str(error)

        for key in (
            "mark_price",
            "index_price",
            "last_funding_rate",
            "basis_percent"
        ):
            result[key] = unavailable(reason)

        result["next_funding_time"] = None

    # Open Interest
    oi, oi_error = safe_fetch(
        f"{base}/fapi/v1/openInterest?symbol={symbol}"
    )

    if oi:
        result["open_interest_contracts"] = metric(
            oi.get("openInterest"),
            "contracts",
            "Binance USD-M Futures"
        )
    else:
        result["open_interest_contracts"] = unavailable(
            "Open Interest unavailable: " + str(oi_error)
        )

    # Recent funding history
    history, history_error = safe_fetch(
        f"{base}/fapi/v1/fundingRate?symbol={symbol}&limit=8"
    )

    if isinstance(history, list) and history:
        result["funding_history_percent"] = [
            float(item["fundingRate"]) * 100
            for item in history
            if item.get("fundingRate") is not None
        ]
        result["funding_history_status"] = "OK"
    else:
        result["funding_history_percent"] = []
        result["funding_history_status"] = "UNAVAILABLE"
        result["funding_history_reason"] = str(history_error)

    result["liquidation_clusters"] = unavailable(
        "Aggregated liquidation heatmap requires a dedicated provider."
    )

    return result


def get_spot_activity():
    url = (
        "https://data-api.binance.vision"
        "/api/v3/ticker/24hr"
    )

    rows, error = safe_fetch(url)

    if not isinstance(rows, list):
        return {
            "status": "UNAVAILABLE",
            "reason": str(error),
            "volume_leaders_24h": [],
            "breadth": unavailable(str(error))
        }

    valid = []
    advancing = 0
    declining = 0

    excluded = ("UPUSDT", "DOWNUSDT", "BULLUSDT", "BEARUSDT")

    for item in rows:
        symbol = item.get("symbol", "")

        if not symbol.endswith("USDT"):
            continue

        if any(tag in symbol for tag in excluded):
            continue

        try:
            quote_volume = float(item.get("quoteVolume", 0))
            change = float(item.get("priceChangePercent", 0))
            trades = int(item.get("count", 0))

            if quote_volume <= 0:
                continue

            valid.append({
                "symbol": symbol,
                "quote_volume_24h": quote_volume,
                "change_24h_pct": change,
                "trades": trades
            })

            if change > 0:
                advancing += 1
            elif change < 0:
                declining += 1

        except (TypeError, ValueError):
            continue

    valid.sort(
        key=lambda item: item["quote_volume_24h"],
        reverse=True
    )

    total = advancing + declining

    breadth = {
        "advancing_pairs": advancing,
        "declining_pairs": declining,
        "measured_pairs": total,
        "advance_decline_ratio": (
            round(advancing / declining, 3)
            if declining else None
        ),
        "status": "OK",
        "source": "Binance Spot 24h ticker",
        "fetched_at": utc_now()
    }

    return {
        "status": "OK",
        "volume_leaders_24h": valid[:12],
        "breadth": breadth,
        "note": (
            "২৪ ঘণ্টার ভলিউম লিডার; "
            "এটি ৫ মিনিট বা ১ ঘণ্টার volume spike নয়।"
        )
    }


def main():
    DATA_DIR.mkdir(parents=True, exist_ok=True)

    result = {
        "schema_version": 1,
        "engine": "Advanced Crypto Intelligence",
        "engine_version": "1.0.0",
        "generated_at": utc_now(),

        "data_policy": (
            "Unavailable data is null. "
            "Never interpret missing data as zero."
        ),

        "etf_flows": unavailable(
            "Verified ETF flow provider is not configured."
        ),

        "on_chain": {
            "mvrv_z_score": unavailable(
                "Requires a verified on-chain data provider."
            ),
            "nupl": unavailable(
                "Requires a verified on-chain data provider."
            ),
            "exchange_netflow": unavailable(
                "Requires a verified exchange-flow provider."
            ),
            "whale_activity": unavailable(
                "Requires verified entity-labelled wallet data."
            )
        },

        "liquidation_heatmap": unavailable(
            "Requires a dedicated liquidation heatmap provider."
        ),

        "derivatives": {
            "BTCUSDT": get_derivatives("BTCUSDT"),
            "ETHUSDT": get_derivatives("ETHUSDT")
        },

        "spot_market_activity": get_spot_activity(),

        "portfolio": {
            "status": "LOCAL_ONLY",
            "note": (
                "Portfolio calculations are performed "
                "in the browser from user-entered holdings."
            )
        }
    }

    temporary_file = OUTPUT_FILE.with_suffix(".tmp")

    temporary_file.write_text(
        json.dumps(
            result,
            ensure_ascii=False,
            indent=2,
            allow_nan=False
        ) + "\n",
        encoding="utf-8"
    )

    temporary_file.replace(OUTPUT_FILE)

    print("Advanced data successfully written:", OUTPUT_FILE)


if __name__ == "__main__":
    main()
