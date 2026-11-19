
#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
FREE ADVANCED CRYPTO INTELLIGENCE ENGINE
Version: 2.3.0

Free public data sources:
- Binance Spot API
- CoinBoss public derivatives API
- Mempool.space
- Coin Metrics Community API

No API key required.
No synthetic data.
Unavailable data remains explicitly unavailable.
Futures data is sentiment context only, never a Spot trade signal.
"""

import json
import math
import time

from datetime import datetime, timezone
from pathlib import Path
from urllib.request import Request, urlopen
from urllib.error import HTTPError, URLError


BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / "data"
OUTPUT_FILE = DATA_DIR / "advanced_data.json"

TIMEOUT = 20
RETRIES = 3

BINANCE = "https://data-api.binance.vision"
COINBOSS = "https://www.coinboss.com/api"
MEMPOOL = "https://mempool.space/api"
COINMETRICS = "https://community-api.coinmetrics.io/v4"

USER_AGENT = "CryptoMacroDashboard-FreeEngine/2.3.0"
HALVING_INTERVAL = 210000


def utc_now():
    return (
        datetime.now(timezone.utc)
        .replace(microsecond=0)
        .isoformat()
        .replace("+00:00", "Z")
    )


def fetch_url(url):
    request = Request(
        url,
        headers={
            "User-Agent": USER_AGENT,
            "Accept": "application/json"
        }
    )

    last_error = None

    for attempt in range(RETRIES):
        try:
            with urlopen(request, timeout=TIMEOUT) as response:
                return response.read().decode("utf-8")

        except (
            HTTPError,
            URLError,
            TimeoutError,
            OSError
        ) as error:
            last_error = str(error)

            if attempt < RETRIES - 1:
                time.sleep(attempt + 1)

    raise RuntimeError(last_error or "Request failed")


def fetch_json(url):
    try:
        return json.loads(fetch_url(url))
    except json.JSONDecodeError as error:
        raise RuntimeError(f"Invalid JSON: {error}")


def fetch_text(url):
    return fetch_url(url).strip()


def finite(value):
    try:
        number = float(value)
        if math.isfinite(number):
            return number
    except (TypeError, ValueError, OverflowError):
        pass

    return None


def metric(value, unit, source, observed_at=None):
    number = finite(value)

    if number is None:
        return unavailable("Valid numeric data unavailable")

    result = {
        "value": number,
        "unit": unit,
        "status": "OK",
        "source": source,
        "fetched_at": utc_now()
    }

    if observed_at is not None:
        result["observed_at"] = observed_at

    return result


def unavailable(reason):
    return {
        "value": None,
        "status": "UNAVAILABLE",
        "reason": str(reason or "Data unavailable")[:250],
        "fetched_at": utc_now()
    }


def safe_fetch(url):
    try:
        data = fetch_json(url)

        if isinstance(data, dict) and data.get("success") is False:
            return None, data.get("error") or data.get("code") or "API returned success=false"

        return data, None

    except Exception as error:
        return None, str(error)[:250]


def unix_ms_to_iso(value):
    try:
        number = finite(value)
        if number is None:
            return None

        return (
            datetime.fromtimestamp(
                number / 1000,
                tz=timezone.utc
            )
            .replace(microsecond=0)
            .isoformat()
            .replace("+00:00", "Z")
        )
    except (ValueError, OverflowError, OSError):
        return None


# ============================================================
# BINANCE SPOT ORDER BOOK
# ============================================================

def get_order_book(symbol):
    url = f"{BINANCE}/api/v3/depth?symbol={symbol}&limit=100"
    data, error = safe_fetch(url)

    if not isinstance(data, dict):
        return {
            "symbol": symbol,
            "imbalance_percent": unavailable(error),
            "bid_value_usdt": unavailable(error),
            "ask_value_usdt": unavailable(error)
        }

    try:
        bid_value = 0.0
        ask_value = 0.0

        for price, quantity in data.get("bids", []):
            p = finite(price)
            q = finite(quantity)

            if p is None or q is None or p < 0 or q < 0:
                raise ValueError("Invalid bid data")

            bid_value += p * q

        for price, quantity in data.get("asks", []):
            p = finite(price)
            q = finite(quantity)

            if p is None or q is None or p < 0 or q < 0:
                raise ValueError("Invalid ask data")

            ask_value += p * q

        total = bid_value + ask_value

        if total <= 0:
            raise ValueError("Empty order book")

        imbalance = ((bid_value - ask_value) / total) * 100

        return {
            "symbol": symbol,
            "imbalance_percent": metric(
                imbalance, "%", "Binance Spot Order Book"
            ),
            "bid_value_usdt": metric(
                bid_value, "USDT", "Binance Spot Order Book"
            ),
            "ask_value_usdt": metric(
                ask_value, "USDT", "Binance Spot Order Book"
            ),
            "last_update_id": data.get("lastUpdateId")
        }

    except Exception as error:
        reason = str(error)

        return {
            "symbol": symbol,
            "imbalance_percent": unavailable(reason),
            "bid_value_usdt": unavailable(reason),
            "ask_value_usdt": unavailable(reason)
        }


# ============================================================
# BINANCE SPOT TAKER BUY / SELL
# ============================================================

def get_taker_ratio(symbol):
    url = (
        f"{BINANCE}/api/v3/klines"
        f"?symbol={symbol}&interval=15m&limit=3"
    )

    data, error = safe_fetch(url)

    if not isinstance(data, list) or len(data) < 2:
        return {
            "symbol": symbol,
            "interval": "15m",
            "taker_buy_sell_ratio": unavailable(error),
            "taker_buy_quote_volume": unavailable(error),
            "taker_sell_quote_volume": unavailable(error)
        }

    try:
        candle = data[-2]

        total_quote = finite(candle[7])
        taker_buy_quote = finite(candle[10])

        if total_quote is None or taker_buy_quote is None:
            raise ValueError("Invalid candle volume")

        taker_sell_quote = total_quote - taker_buy_quote

        if (
            total_quote <= 0
            or taker_buy_quote < 0
            or taker_sell_quote < 0
        ):
            raise ValueError("Invalid taker volume")

        ratio = (
            metric(
                taker_buy_quote / taker_sell_quote,
                "ratio",
                "Binance Spot 15m Kline",
                candle[6]
            )
            if taker_sell_quote > 0
            else unavailable("Sell volume is zero")
        )

        return {
            "symbol": symbol,
            "interval": "15m",
            "candle_close_time": candle[6],
            "taker_buy_sell_ratio": ratio,
            "taker_buy_quote_volume": metric(
                taker_buy_quote,
                "USDT",
                "Binance Spot 15m Kline",
                candle[6]
            ),
            "taker_sell_quote_volume": metric(
                taker_sell_quote,
                "USDT",
                "Binance Spot 15m Kline",
                candle[6]
            )
        }

    except Exception as error:
        reason = str(error)

        return {
            "symbol": symbol,
            "interval": "15m",
            "taker_buy_sell_ratio": unavailable(reason),
            "taker_buy_quote_volume": unavailable(reason),
            "taker_sell_quote_volume": unavailable(reason)
        }


# ============================================================
# COINBOSS CROSS-EXCHANGE DERIVATIVES
# ============================================================

def coinboss_fetch(path, coin):
    url = f"{COINBOSS}{path}?coin={coin}"
    data, error = safe_fetch(url)

    if not isinstance(data, dict):
        return None, error or "Invalid CoinBoss response"

    if data.get("success") is not True:
        return None, data.get("error") or "CoinBoss request unsuccessful"

    return data, None


def get_coinboss_open_interest(coin):
    data, error = coinboss_fetch("/sd/oi", coin)

    if data is None:
        return {
            "total_usd": unavailable(error),
            "total_change_24h_pct": unavailable(error),
            "exchange_count": unavailable(error),
            "contract_count": unavailable(error),
            "coverage": None,
            "asof": None
        }

    return {
        "total_usd": metric(
            data.get("total_usd"),
            "USD",
            "CoinBoss Cross-exchange Open Interest",
            unix_ms_to_iso(data.get("asof"))
        ),
        "total_change_24h_pct": metric(
            (data.get("change") or {}).get("pct_24h"),
            "%",
            "CoinBoss Cross-exchange Open Interest"
        ),
        "exchange_count": metric(
            data.get("n_exchanges"),
            "exchanges",
            "CoinBoss"
        ),
        "contract_count": metric(
            data.get("n_contracts"),
            "contracts",
            "CoinBoss"
        ),
        "coverage": data.get("coverage"),
        "method": data.get("method"),
        "asof": unix_ms_to_iso(data.get("asof")),
        "provider": "CoinBoss"
    }


def get_coinboss_funding(coin):
    data, error = coinboss_fetch("/sd/funding", coin)

    if data is None:
        return {
            "avg_8h": unavailable(error),
            "oi_weighted_8h": unavailable(error),
            "apr_pct": unavailable(error),
            "exchange_count": unavailable(error),
            "coverage": None,
            "asof": None
        }

    return {
        "avg_8h": metric(
            data.get("avg_8h"),
            "fraction per 8h",
            "CoinBoss Cross-exchange Funding"
        ),
        "oi_weighted_8h": metric(
            data.get("oi_weighted_8h"),
            "fraction per 8h",
            "CoinBoss Cross-exchange Funding"
        ),
        "apr_pct": metric(
            data.get("apr_pct"),
            "% per year",
            "CoinBoss Cross-exchange Funding"
        ),
        "exchange_count": metric(
            data.get("n_exchanges"),
            "exchanges",
            "CoinBoss"
        ),
        "coverage": data.get("coverage"),
        "method": data.get("method"),
        "asof": unix_ms_to_iso(data.get("now")),
        "provider": "CoinBoss",
        "unit_note": (
            "Funding rate is a fraction; 0.0001 = 0.01%. "
            "OI-weighted 8h rate is preferred."
        )
    }


def get_coinboss_long_short(coin):
    data, error = coinboss_fetch("/sd/ls", coin)

    if data is None:
        return {
            "account": unavailable(error),
            "position": unavailable(error),
            "taker": unavailable(error),
            "coverage": None,
            "provider": "CoinBoss"
        }

    # The endpoint keeps account, position and taker measures separate.
    # Do not mix different ratio types into one figure.
    result = {
        "account": unavailable("Account ratio not present in response"),
        "position": unavailable("Position ratio not present in response"),
        "taker": unavailable("Taker ratio not present in response"),
        "coverage": data.get("coverage"),
        "provider": "CoinBoss",
        "asof": unix_ms_to_iso(data.get("now")),
        "raw_schema": data.get("schema")
    }

    rows = data.get("data", [])

    if isinstance(rows, list):
        account_rows = []
        position_rows = []
        taker_rows = []

        for row in rows:
            if not isinstance(row, dict):
                continue

            flavour = str(
                row.get("flavour")
                or row.get("type")
                or row.get("kind")
                or ""
            ).lower()

            exchange = row.get("exchange")
            long_ratio = finite(row.get("long_ratio"))
            short_ratio = finite(row.get("short_ratio"))
            ratio = finite(row.get("long_short_ratio"))

            if ratio is None and long_ratio is not None and short_ratio:
                if short_ratio > 0:
                    ratio = long_ratio / short_ratio

            item = {
                "exchange": exchange,
                "ratio": ratio,
                "long_ratio": long_ratio,
                "short_ratio": short_ratio,
                "timestamp": unix_ms_to_iso(
                    row.get("timestamp")
                    or row.get("observed_at")
                )
            }

            if "account" in flavour:
                account_rows.append(item)
            elif "position" in flavour:
                position_rows.append(item)
            elif "taker" in flavour:
                taker_rows.append(item)

        def summarize(rows, label):
            valid = [
                row for row in rows
                if finite(row.get("ratio")) is not None
            ]

            if not valid:
                return unavailable(
                    f"No verified {label} ratio rows returned"
                )

            ratios = [row["ratio"] for row in valid]

            return {
                "value": sum(ratios) / len(ratios),
                "unit": "long/short ratio",
                "status": "OK",
                "source": "CoinBoss Cross-exchange Long/Short",
                "exchange_count": len(valid),
                "exchanges": valid,
                "fetched_at": utc_now()
            }

        result["account"] = summarize(account_rows, "account")
        result["position"] = summarize(position_rows, "position")
        result["taker"] = summarize(taker_rows, "taker")

    # Some schema revisions may expose separate arrays or aggregate
    # fields. Do not guess their meaning; leave unavailable if unrecognised.
    return result


def get_derivatives(symbol):
    coin = symbol.replace("USDT", "")

    oi = get_coinboss_open_interest(coin)
    funding = get_coinboss_funding(coin)
    long_short = get_coinboss_long_short(coin)

    return {
        "symbol": symbol,
        "provider": "CoinBoss",
        "data_type": (
            "Cross-exchange Futures sentiment only; "
            "not Spot market data"
        ),

        # Compatible field names for existing dashboard consumers.
        "open_interest_usd": oi["total_usd"],
        "open_interest_change_24h_pct": oi["total_change_24h_pct"],
        "open_interest_contracts": oi["contract_count"],
        "open_interest_exchange_count": oi["exchange_count"],

        "last_funding_rate": funding["oi_weighted_8h"],
        "funding_avg_8h": funding["avg_8h"],
        "funding_apr_pct": funding["apr_pct"],
        "funding_exchange_count": funding["exchange_count"],

        "global_long_short_ratio": long_short["account"],
        "position_long_short_ratio": long_short["position"],
        "taker_long_short_ratio": long_short["taker"],

        # Legacy fields remain explicitly unavailable because
        # CoinBoss aggregate does not provide these Binance fields.
        "mark_price": unavailable(
            "Not included in selected CoinBoss aggregate endpoint"
        ),
        "index_price": unavailable(
            "Not included in selected CoinBoss aggregate endpoint"
        ),

        "liquidation_clusters": unavailable(
            "Verified liquidation heatmap integration not configured"
        ),

        "coverage": {
            "open_interest": oi.get("coverage"),
            "funding": funding.get("coverage"),
            "long_short": long_short.get("coverage")
        },

        "asof": {
            "open_interest": oi.get("asof"),
            "funding": funding.get("asof"),
            "long_short": long_short.get("asof")
        },

        "provider_note": (
            "CoinBoss aggregates data from multiple derivatives venues. "
            "Long/short measures are kept separate. "
            "Futures metrics are context only, not Spot signals."
        )
    }


# ============================================================
# MEMPOOL BITCOIN MINING DATA
# ============================================================

def get_mining_data():
    data, error = safe_fetch(
        f"{MEMPOOL}/v1/mining/hashrate/3d"
    )

    if not isinstance(data, dict):
        return {
            "hashrate": unavailable(error),
            "difficulty": unavailable(error),
            "estimated_hashrate": unavailable(error)
        }

    return {
        "hashrate": metric(
            data.get("currentHashrate"),
            "H/s",
            "Mempool.space"
        ),
        "difficulty": metric(
            data.get("currentDifficulty"),
            "difficulty",
            "Mempool.space"
        ),
        "estimated_hashrate": metric(
            data.get("estimatedHashrate"),
            "H/s",
            "Mempool.space"
        )
    }


# ============================================================
# BITCOIN HALVING COUNTDOWN
# ============================================================

def get_halving():
    try:
        height = int(fetch_text(f"{MEMPOOL}/blocks/tip/height"))

        if height < 0:
            raise ValueError("Invalid Bitcoin block height")

        next_halving = (
            (height // HALVING_INTERVAL) + 1
        ) * HALVING_INTERVAL

        remaining = max(0, next_halving - height)
        estimated_days = remaining * 10 / 1440

        return {
            "current_block_height": height,
            "next_halving_block": next_halving,
            "blocks_remaining": remaining,
            "estimated_days_remaining": round(estimated_days, 2),
            "estimated_years_remaining": round(
                estimated_days / 365.25, 2
            ),
            "status": "OK",
            "source": "Mempool.space",
            "note": (
                "আনুমানিক সময়; প্রকৃত Halving নির্ধারিত "
                "হবে Block Height অনুযায়ী।"
            ),
            "fetched_at": utc_now()
        }

    except Exception as error:
        return {
            "current_block_height": None,
            "next_halving_block": None,
            "blocks_remaining": None,
            "estimated_days_remaining": None,
            "estimated_years_remaining": None,
            "status": "UNAVAILABLE",
            "reason": str(error)[:250],
            "fetched_at": utc_now()
        }


# ============================================================
# COIN METRICS COMMUNITY API - MVRV
# ============================================================

def get_mvrv():
    url = (
        f"{COINMETRICS}/timeseries/asset-metrics"
        "?assets=btc"
        "&metrics=CapMVRVCur"
        "&frequency=1d"
        "&page_size=2"
    )

    data, error = safe_fetch(url)

    if not isinstance(data, dict):
        return {
            "mvrv_ratio": unavailable(error),
            "mvrv_z_score": unavailable(
                "MVRV Z-Score unavailable"
            )
        }

    rows = data.get("data", [])

    if not rows:
        return {
            "mvrv_ratio": unavailable(
                "No MVRV observation returned"
            ),
            "mvrv_z_score": unavailable(
                "MVRV Z-Score not supplied by this metric"
            )
        }

    latest = rows[-1]

    ratio = metric(
        latest.get("CapMVRVCur"),
        "ratio",
        "Coin Metrics Community API",
        latest.get("time")
    )

    ratio["observation_date"] = latest.get("time")

    return {
        "mvrv_ratio": ratio,
        "mvrv_z_score": unavailable(
            "CapMVRVCur is MVRV Ratio, not MVRV Z-Score"
        )
    }


# ============================================================
# BINANCE SPOT MARKET BREADTH
# ============================================================

def get_spot_activity():
    rows, error = safe_fetch(
        f"{BINANCE}/api/v3/ticker/24hr"
    )

    if not isinstance(rows, list):
        return {
            "status": "UNAVAILABLE",
            "reason": str(error),
            "volume_leaders_24h": [],
            "breadth": unavailable(error)
        }

    valid = []
    advancing = 0
    declining = 0
    unchanged = 0

    excluded = (
        "UPUSDT",
        "DOWNUSDT",
        "BULLUSDT",
        "BEARUSDT"
    )

    for item in rows:
        symbol = item.get("symbol", "")

        if not symbol.endswith("USDT"):
            continue

        if any(tag in symbol for tag in excluded):
            continue

        quote_volume = finite(item.get("quoteVolume"))
        change = finite(item.get("priceChangePercent"))
        trades = finite(item.get("count"))

        if (
            quote_volume is None
            or change is None
            or trades is None
            or quote_volume <= 0
        ):
            continue

        valid.append({
            "symbol": symbol,
            "quote_volume_24h": quote_volume,
            "change_24h_pct": change,
            "trades": int(trades)
        })

        if change > 0:
            advancing += 1
        elif change < 0:
            declining += 1
        else:
            unchanged += 1

    valid.sort(
        key=lambda item: item["quote_volume_24h"],
        reverse=True
    )

    measured = advancing + declining + unchanged

    if measured == 0:
        return {
            "status": "UNAVAILABLE",
            "reason": "No valid USDT Spot pairs returned",
            "volume_leaders_24h": [],
            "breadth": unavailable(
                "No valid Spot breadth observations"
            )
        }

    breadth = {
        "advancing_pairs": advancing,
        "declining_pairs": declining,
        "unchanged_pairs": unchanged,
        "measured_pairs": measured,
        "advance_decline_ratio": (
            round(advancing / declining, 3)
            if declining > 0
            else None
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
            "২৪ ঘণ্টার Spot Market Breadth; "
            "USDT trading pairs-এর উপর ভিত্তি করে।"
        )
    }


# ============================================================
# MAIN ENGINE
# ============================================================

def main():
    DATA_DIR.mkdir(parents=True, exist_ok=True)

    print("Starting Free Advanced Crypto Engine v2.3.0")

    print("Fetching Spot Order Books...")
    order_books = {
        "BTCUSDT": get_order_book("BTCUSDT"),
        "ETHUSDT": get_order_book("ETHUSDT")
    }

    print("Fetching Spot Taker Ratios...")
    taker_ratios = {
        "BTCUSDT": get_taker_ratio("BTCUSDT"),
        "ETHUSDT": get_taker_ratio("ETHUSDT")
    }

    print("Fetching Bitcoin Mining Data...")
    mining = get_mining_data()

    print("Fetching Bitcoin Halving...")
    halving = get_halving()

    print("Fetching MVRV...")
    mvrv = get_mvrv()

    print("Fetching Spot Market Breadth...")
    spot_activity = get_spot_activity()

    print("Fetching CoinBoss Cross-exchange Derivatives...")
    derivatives = {
        "BTCUSDT": get_derivatives("BTCUSDT"),
        "ETHUSDT": get_derivatives("ETHUSDT")
    }

    result = {
        "schema_version": 2,
        "engine": "Free Advanced Crypto Intelligence",
        "engine_version": "2.3.0",
        "generated_at": utc_now(),

        "data_policy": (
            "Free public APIs only. "
            "Unavailable data remains null. "
            "No synthetic values. "
            "Futures data is sentiment context only."
        ),

        "data_sources": [
            "Binance Spot Public API",
            "CoinBoss Public Derivatives API",
            "Mempool.space",
            "Coin Metrics Community API"
        ],

        "etf_flows": unavailable(
            "ETF flow integration not configured"
        ),

        "on_chain": {
            "mvrv_ratio": mvrv["mvrv_ratio"],
            "mvrv_z_score": mvrv["mvrv_z_score"],

            "sth_sopr": unavailable(
                "No verified free STH SOPR source configured"
            ),

            "nupl": unavailable(
                "No verified free NUPL source configured"
            ),

            "exchange_netflow": unavailable(
                "No verified free exchange flow source configured"
            ),

            "stablecoin_supply": unavailable(
                "No verified free stablecoin supply source configured"
            ),

            "whale_activity": unavailable(
                "Entity-labelled whale data unavailable"
            ),

            "hashrate": mining["hashrate"],
            "mining_difficulty": mining["difficulty"],
            "estimated_hashrate": mining["estimated_hashrate"]
        },

        "halving": halving,
        "spot_market_activity": spot_activity,
        "spot_order_book": order_books,
        "spot_taker_activity": taker_ratios,
        "derivatives": derivatives,

        "liquidation_heatmap": unavailable(
            "Verified liquidation heatmap integration not configured"
        ),

        "portfolio": {
            "status": "LOCAL_ONLY",
            "note": (
                "Portfolio data is not uploaded to external providers."
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

    print("----------------------------------")
    print("FREE ADVANCED ENGINE SUCCESS")
    print("Output:", OUTPUT_FILE)
    print("Version: 2.3.0")
    print("----------------------------------")


if __name__ == "__main__":
    main()
