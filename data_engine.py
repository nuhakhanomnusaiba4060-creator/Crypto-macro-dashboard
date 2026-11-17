
#!/usr/bin/env python3
"""Crypto Macro Dashboard - public market data engine.

Sources:
- CoinGecko: global market statistics and BTC/ETH reference prices
- Alternative.me: Fear & Greed Index
- Binance Spot public API: fully closed daily BTC/ETH candles

No API keys required. Missing/stale data is never fabricated.
"""

from __future__ import annotations

import json
import math
import os
import tempfile
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

SCHEMA_VERSION = 2
OUTPUT_FILE = Path(os.getenv("DASHBOARD_DATA_FILE", "data/market_data.json"))
TIMEOUT_SECONDS = 15
USER_AGENT = "CryptoMacroDashboard/1.1"

BINANCE_BASE = "https://data-api.binance.vision"
COINGECKO_BASE = "https://api.coingecko.com/api/v3"
ALTERNATIVE_BASE = "https://api.alternative.me"


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(
        timespec="seconds"
    ).replace("+00:00", "Z")


def finite_number(value: Any) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError, OverflowError):
        return None
    return number if math.isfinite(number) else None


def http_json(
    url: str,
    params: dict[str, Any] | None = None
) -> tuple[Any, str]:

    if params:
        url = f"{url}?{urlencode(params)}"

    request = Request(
        url,
        headers={
            "User-Agent": USER_AGENT,
            "Accept": "application/json"
        }
    )

    last_error = "Unknown network error"

    for attempt in range(3):
        try:
            with urlopen(
                request,
                timeout=TIMEOUT_SECONDS
            ) as response:
                payload = response.read()

            return json.loads(payload.decode("utf-8")), utc_now()

        except HTTPError as exc:
            last_error = f"HTTP_{exc.code}"

            if exc.code not in (
                429, 500, 502, 503, 504
            ) or attempt == 2:
                break

        except (
            URLError,
            TimeoutError,
            OSError,
            json.JSONDecodeError
        ) as exc:

            last_error = f"{type(exc).__name__}: {exc}"

            if attempt == 2:
                break

        time.sleep(1.5 * (attempt + 1))

    raise RuntimeError(last_error)


def metric(
    value: Any = None,
    unit: str | None = None,
    source: str | None = None,
    source_updated_at: str | None = None,
    status: str = "OK",
    error: str | None = None,
    fetched_at: str | None = None,
) -> dict[str, Any]:

    number = (
        finite_number(value)
        if value is not None
        else None
    )

    if value is not None and number is None:
        status = "INVALID_DATA"
        error = "Provider returned invalid numeric data"

    if number is None and status == "OK":
        status = "UNAVAILABLE"

    return {
        "value": number,
        "unit": unit,
        "source": source,
        "source_updated_at": source_updated_at,
        "fetched_at": fetched_at or utc_now(),
        "status": status,
        "error": error,
    }


def unavailable(source: str, error: str) -> dict[str, Any]:
    return metric(
        source=source,
        status="UNAVAILABLE",
        error=error[:240]
    )


def timestamp_from_seconds(value: Any) -> str | None:
    try:
        return datetime.fromtimestamp(
            int(value),
            timezone.utc
        ).isoformat(
            timespec="seconds"
        ).replace("+00:00", "Z")

    except (
        TypeError, ValueError, OverflowError, OSError
    ):
        return None


def timestamp_from_milliseconds(value: Any) -> str | None:
    try:
        return datetime.fromtimestamp(
            int(value) / 1000,
            timezone.utc
        ).isoformat(
            timespec="seconds"
        ).replace("+00:00", "Z")

    except (
        TypeError, ValueError, OverflowError, OSError
    ):
        return None


def age_status(
    timestamp: str | None,
    stale_after_seconds: int
) -> str:

    if not timestamp:
        return "TIMESTAMP_UNKNOWN"

    try:
        updated = datetime.fromisoformat(
            timestamp.replace("Z", "+00:00")
        )

        age = (
            datetime.now(timezone.utc) - updated
        ).total_seconds()

        if age < -300:
            return "TIMESTAMP_INVALID"

        return (
            "STALE"
            if age > stale_after_seconds
            else "OK"
        )

    except (TypeError, ValueError):
        return "TIMESTAMP_INVALID"


def fetch_global_market() -> dict[str, Any]:

    source = "CoinGecko API"

    keys = (
        "total_market_cap_usd",
        "total_volume_24h_usd",
        "btc_dominance_pct",
        "eth_dominance_pct",
        "active_cryptocurrencies",
        "markets_count",
    )

    try:
        data, fetched_at = http_json(
            f"{COINGECKO_BASE}/global"
        )

        market_data = data.get("data", {})

        if not isinstance(market_data, dict) or not market_data:
            raise ValueError("Missing global market payload")

        updated_at = timestamp_from_seconds(
            market_data.get("updated_at")
        )

        status = age_status(updated_at, 7200)

        fields = {
            "total_market_cap_usd": (
                market_data.get(
                    "total_market_cap", {}
                ).get("usd"),
                "USD"
            ),
            "total_volume_24h_usd": (
                market_data.get(
                    "total_volume", {}
                ).get("usd"),
                "USD"
            ),
            "btc_dominance_pct": (
                market_data.get(
                    "market_cap_percentage", {}
                ).get("btc"),
                "%"
            ),
            "eth_dominance_pct": (
                market_data.get(
                    "market_cap_percentage", {}
                ).get("eth"),
                "%"
            ),
            "active_cryptocurrencies": (
                market_data.get("active_cryptocurrencies"),
                "count"
            ),
            "markets_count": (
                market_data.get("markets"),
                "count"
            ),
        }

        result = {}

        for key, (value, unit) in fields.items():
            result[key] = metric(
                value,
                unit,
                source,
                updated_at,
                status,
                fetched_at=fetched_at
            )

        return result

    except Exception as exc:
        return {
            key: unavailable(source, str(exc))
            for key in keys
        }


def fetch_fear_greed() -> dict[str, Any]:

    source = "Alternative.me Fear & Greed API"

    try:
        data, fetched_at = http_json(
            f"{ALTERNATIVE_BASE}/fng/",
            {
                "limit": 1,
                "format": "json"
            }
        )

        rows = data.get("data", [])

        if not rows:
            raise ValueError("No Fear & Greed observation")

        row = rows[0]
        value = finite_number(row.get("value"))

        if value is None or not 0 <= value <= 100:
            raise ValueError(
                "Fear & Greed value outside 0-100"
            )

        updated_at = timestamp_from_seconds(
            row.get("timestamp")
        )

        status = age_status(
            updated_at,
            48 * 3600
        )

        return {
            "value": value,
            "classification": str(
                row.get("value_classification", "Unknown")
            ),
            "unit": "/100",
            "source": source,
            "source_updated_at": updated_at,
            "fetched_at": fetched_at,
            "status": status,
            "error": None,
        }

    except Exception as exc:
        return {
            "value": None,
            "classification": None,
            "unit": "/100",
            "source": source,
            "source_updated_at": None,
            "fetched_at": utc_now(),
            "status": "UNAVAILABLE",
            "error": str(exc)[:240],
        }


def sma(
    values: list[float],
    period: int
) -> float | None:

    if len(values) < period:
        return None

    return sum(values[-period:]) / period


def ema_series(
    values: list[float],
    period: int
) -> list[float | None]:

    result: list[float | None] = [None] * len(values)

    if len(values) < period:
        return result

    previous = sum(values[:period]) / period
    result[period - 1] = previous

    multiplier = 2.0 / (period + 1)

    for index in range(period, len(values)):
        previous = (
            (values[index] - previous) * multiplier
            + previous
        )

        result[index] = previous

    return result


def calculate_rsi(
    values: list[float],
    period: int = 14
) -> float | None:

    if len(values) < period + 1:
        return None

    changes = [
        values[i] - values[i - 1]
        for i in range(1, len(values))
    ]

    gains = [
        max(change, 0.0)
        for change in changes
    ]

    losses = [
        max(-change, 0.0)
        for change in changes
    ]

    average_gain = sum(gains[:period]) / period
    average_loss = sum(losses[:period]) / period

    for index in range(period, len(gains)):

        average_gain = (
            average_gain * (period - 1)
            + gains[index]
        ) / period

        average_loss = (
            average_loss * (period - 1)
            + losses[index]
        ) / period

    if average_loss == 0:
        return 100.0 if average_gain > 0 else 50.0

    relative_strength = average_gain / average_loss

    return 100.0 - (
        100.0 / (1.0 + relative_strength)
    )


def calculate_macd(
    values: list[float]
) -> tuple[
    float | None,
    float | None,
    float | None
]:

    fast = ema_series(values, 12)
    slow = ema_series(values, 26)

    macd_values = []

    for fast_value, slow_value in zip(fast, slow):

        if fast_value is not None and slow_value is not None:
            macd_values.append(fast_value - slow_value)

    if len(macd_values) < 9:
        return None, None, None

    signal_values = ema_series(macd_values, 9)

    macd_value = macd_values[-1]
    signal_value = signal_values[-1]

    if signal_value is None:
        return macd_value, None, None

    return (
        macd_value,
        signal_value,
        macd_value - signal_value
    )


def calculate_adx(
    highs: list[float],
    lows: list[float],
    closes: list[float],
    period: int = 14
) -> float | None:

    if len(closes) < period + 1:
        return None

    true_ranges = []
    positive_dm = []
    negative_dm = []

    for i in range(1, len(closes)):

        up_move = highs[i] - highs[i - 1]
        down_move = lows[i - 1] - lows[i]

        positive_dm.append(
            up_move
            if up_move > down_move and up_move > 0
            else 0.0
        )

        negative_dm.append(
            down_move
            if down_move > up_move and down_move > 0
            else 0.0
        )

        true_ranges.append(
            max(
                highs[i] - lows[i],
                abs(highs[i] - closes[i - 1]),
                abs(lows[i] - closes[i - 1])
            )
        )

    if len(true_ranges) < period:
        return None

    smoothed_tr = sum(true_ranges[:period])
    smoothed_plus = sum(positive_dm[:period])
    smoothed_minus = sum(negative_dm[:period])

    dx_values = []

    for i in range(period - 1, len(true_ranges)):

        if i > period - 1:

            smoothed_tr = (
                smoothed_tr
                - smoothed_tr / period
                + true_ranges[i]
            )

            smoothed_plus = (
                smoothed_plus
                - smoothed_plus / period
                + positive_dm[i]
            )

            smoothed_minus = (
                smoothed_minus
                - smoothed_minus / period
                + negative_dm[i]
            )

        if smoothed_tr <= 0:
            continue

        plus_di = 100.0 * smoothed_plus / smoothed_tr
        minus_di = 100.0 * smoothed_minus / smoothed_tr

        denominator = plus_di + minus_di

        dx_values.append(
            100.0 * abs(plus_di - minus_di) / denominator
            if denominator > 0
            else 0.0
        )

    if len(dx_values) < period:
        return None

    adx_value = sum(dx_values[:period]) / period

    for dx in dx_values[period:]:
        adx_value = (
            adx_value * (period - 1) + dx
        ) / period

    return adx_value


def calculate_indicators(
    candles: list[dict[str, Any]]
) -> dict[str, Any]:

    closes = [c["close"] for c in candles]
    highs = [c["high"] for c in candles]
    lows = [c["low"] for c in candles]
    volumes = [c["volume"] for c in candles]

    source = "Binance Spot closed 1D candles"

    updated_at = timestamp_from_milliseconds(
        candles[-1]["close_time"]
    )

    fetched_at = utc_now()

    candle_status = age_status(
        updated_at,
        36 * 3600
    )

    def m(value: Any, unit: str) -> dict[str, Any]:
        return metric(
            value,
            unit,
            source,
            updated_at,
            candle_status,
            fetched_at=fetched_at
        )

    bb_mid = sma(closes, 20)
    bb_std = None

    if bb_mid is not None:

        last_twenty = closes[-20:]

        bb_std = math.sqrt(
            sum(
                (x - bb_mid) ** 2
                for x in last_twenty
            ) / 20
        )

    macd_value, macd_signal, macd_histogram = (
        calculate_macd(closes)
    )

    average_volume = sma(volumes, 20)

    return {
        "ma20": m(sma(closes, 20), "USDT"),
        "ma50": m(sma(closes, 50), "USDT"),
        "ma200": m(sma(closes, 200), "USDT"),

        "ema20": m(
            ema_series(closes, 20)[-1],
            "USDT"
        ),

        "ema50": m(
            ema_series(closes, 50)[-1],
            "USDT"
        ),

        "rsi14": m(
            calculate_rsi(closes, 14),
            "index"
        ),

        "macd": m(macd_value, "USDT"),
        "macd_signal": m(macd_signal, "USDT"),
        "macd_histogram": m(macd_histogram, "USDT"),

        "adx14": m(
            calculate_adx(highs, lows, closes, 14),
            "index"
        ),

        "bollinger_upper": m(
            bb_mid + 2 * bb_std
            if bb_mid is not None and bb_std is not None
            else None,
            "USDT"
        ),

        "bollinger_middle": m(bb_mid, "USDT"),

        "bollinger_lower": m(
            bb_mid - 2 * bb_std
            if bb_mid is not None and bb_std is not None
            else None,
            "USDT"
        ),

        "volume_last_closed_day": m(
            volumes[-1],
            "base asset"
        ),

        "volume_sma20": m(
            average_volume,
            "base asset"
        ),

        "volume_ratio_20d": m(
            volumes[-1] / average_volume
            if average_volume is not None and average_volume > 0
            else None,
            "x"
        ),

        "support_20d": m(
            min(lows[-20:])
            if len(lows) >= 20
            else None,
            "USDT"
        ),

        "resistance_20d": m(
            max(highs[-20:])
            if len(highs) >= 20
            else None,
            "USDT"
        )
    }


def fetch_asset(
    symbol: str,
    coin_id: str
) -> dict[str, Any]:

    source = "Binance Spot Public API"

    result: dict[str, Any] = {
        "symbol": symbol,
        "coin_id": coin_id
    }

    indicator_names = (
        "ma20", "ma50", "ma200",
        "ema20", "ema50", "rsi14",
        "macd", "macd_signal", "macd_histogram",
        "adx14",
        "bollinger_upper", "bollinger_middle",
        "bollinger_lower",
        "volume_last_closed_day", "volume_sma20",
        "volume_ratio_20d",
        "support_20d", "resistance_20d"
    )

    try:

        raw, fetched_at = http_json(
            f"{BINANCE_BASE}/api/v3/klines",
            {
                "symbol": f"{symbol}USDT",
                "interval": "1d",
                "limit": 250
            }
        )

        if not isinstance(raw, list):
            raise ValueError(
                "Binance returned an invalid candle payload"
            )

        now_ms = int(time.time() * 1000)
        candles = []

        for row in raw:

            if not isinstance(row, list) or len(row) < 7:
                continue

            try:
                open_time = int(row[0])
                close_time = int(row[6])
            except (TypeError, ValueError, OverflowError):
                continue

            # Exclude the currently forming daily candle.
            if close_time >= now_ms:
                continue

            parsed = [
                finite_number(row[i])
                for i in (1, 2, 3, 4, 5)
            ]

            if any(value is None for value in parsed):
                continue

            open_price, high, low, close, volume = parsed

            if min(open_price, high, low, close) <= 0:
                continue

            if volume < 0:
                continue

            if high < max(open_price, close, low):
                continue

            if low > min(open_price, close, high):
                continue

            candles.append({
                "open_time": open_time,
                "close_time": close_time,
                "open": open_price,
                "high": high,
                "low": low,
                "close": close,
                "volume": volume
            })

        candles.sort(
            key=lambda candle: candle["open_time"]
        )

        if len(candles) < 200:
            raise ValueError(
                f"Only {len(candles)} fully closed valid daily candles; "
                "200 required"
            )

        latest = candles[-1]

        updated_at = timestamp_from_milliseconds(
            latest["close_time"]
        )

        status = age_status(
            updated_at,
            36 * 3600
        )

        indicators = calculate_indicators(candles)

        for item in indicators.values():
            item["fetched_at"] = fetched_at

        result.update({
            "price_usdt": metric(
                latest["close"],
                "USDT",
                source,
                updated_at,
                status,
                fetched_at=fetched_at
            ),

            "candle_interval": "1d",

            "candle_policy": (
                "Only fully closed candles; "
                "current forming candle excluded"
            ),

            "candle_count": len(candles),

            "last_closed_candle_at": updated_at,

            "indicators": indicators
        })

    except Exception as exc:

        error = str(exc)[:240]

        result.update({
            "price_usdt": unavailable(source, error),

            "candle_interval": "1d",

            "candle_policy": (
                "Only fully closed candles; "
                "current forming candle excluded"
            ),

            "candle_count": 0,

            "last_closed_candle_at": None,

            "indicators": {
                name: unavailable(source, error)
                for name in indicator_names
            }
        })

    return result


def fetch_coingecko_prices() -> dict[str, Any]:

    source = "CoinGecko API"

    try:

        data, fetched_at = http_json(
            f"{COINGECKO_BASE}/simple/price",
            {
                "ids": "bitcoin,ethereum",
                "vs_currencies": "usd",
                "include_24hr_change": "true",
                "include_last_updated_at": "true"
            }
        )

        result = {}

        for coin_id in ("bitcoin", "ethereum"):

            item = data.get(coin_id, {})

            updated_at = timestamp_from_seconds(
                item.get("last_updated_at")
            )

            status = age_status(
                updated_at,
                1800
            )

            result[coin_id] = {
                "price_usd": metric(
                    item.get("usd"),
                    "USD",
                    source,
                    updated_at,
                    status,
                    fetched_at=fetched_at
                ),

                "change_24h_pct": metric(
                    item.get("usd_24h_change"),
                    "%",
                    source,
                    updated_at,
                    status,
                    fetched_at=fetched_at
                ),

                "source_updated_at": updated_at,
                "fetched_at": fetched_at
            }

        return result

    except Exception as exc:

        error = str(exc)

        return {
            coin: {
                "price_usd": unavailable(source, error),
                "change_24h_pct": unavailable(source, error),
                "source_updated_at": None,
                "fetched_at": utc_now()
            }
            for coin in ("bitcoin", "ethereum")
        }


def write_json_atomic(
    path: Path,
    payload: dict[str, Any]
) -> None:

    path.parent.mkdir(
        parents=True,
        exist_ok=True
    )

    fd, temp_name = tempfile.mkstemp(
        prefix=f".{path.name}.",
        suffix=".tmp",
        dir=str(path.parent)
    )

    try:

        with os.fdopen(
            fd,
            "w",
            encoding="utf-8"
        ) as handle:

            json.dump(
                payload,
                handle,
                ensure_ascii=False,
                indent=2,
                allow_nan=False
            )

            handle.write("\n")

        os.replace(
            temp_name,
            path
        )

    except Exception:

        try:
            os.unlink(temp_name)
        except OSError:
            pass

        raise


def build_payload() -> dict[str, Any]:

    return {
        "schema_version": SCHEMA_VERSION,

        "generated_at": utc_now(),

        "update_mode": "scheduled_snapshot_not_realtime",

        "data_policy": (
            "Unavailable, stale, or timestamp-unknown values "
            "must not be treated as zero, neutral, or confirmed."
        ),

        "global_market": fetch_global_market(),

        "fear_greed": fetch_fear_greed(),

        "major_assets": fetch_coingecko_prices(),

        "technical": {
            "BTC": fetch_asset("BTC", "bitcoin"),
            "ETH": fetch_asset("ETH", "ethereum")
        },

        "not_integrated_yet": [
            "Fed policy and FOMC",
            "CPI/PCE/NFP",
            "DXY and Treasury yields",
            "VIX and equities",
            "ETF flows",
            "on-chain metrics",
            "whale flows",
            "token unlocks",
            "project fundamentals"
        ]
    }


def main() -> int:

    payload = build_payload()

    write_json_atomic(
        OUTPUT_FILE,
        payload
    )

    print(
        f"Wrote {OUTPUT_FILE} "
        f"at {payload['generated_at']}"
    )

    for name, item in payload["global_market"].items():
        print(
            f"global_market.{name}: "
            f"{item['status']}"
        )

    print(
        f"fear_greed: "
        f"{payload['fear_greed']['status']}"
    )

    for asset, item in payload["technical"].items():

        print(
            f"technical.{asset}.price_usdt: "
            f"{item['price_usdt']['status']}"
        )

        print(
            f"technical.{asset}.closed_candles: "
            f"{item['candle_count']}"
        )

        for indicator, value in item["indicators"].items():
            print(
                f"technical.{asset}.{indicator}: "
                f"{value['status']}"
            )

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
