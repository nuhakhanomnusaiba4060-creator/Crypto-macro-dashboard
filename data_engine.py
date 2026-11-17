
#!/usr/bin/env python3
"""Crypto Macro Dashboard - Public Market Data Engine.

Fetches public CoinGecko, Alternative.me and Binance Spot data.
Writes data/market_data.json. No API keys are required.
Unavailable or stale data is never replaced with fake values.
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


SCHEMA_VERSION = 1
OUTPUT_FILE = Path(os.getenv("DASHBOARD_DATA_FILE", "data/market_data.json"))

TIMEOUT_SECONDS = 15
USER_AGENT = "CryptoMacroDashboard/1.0"

BINANCE_BASE = "https://data-api.binance.vision"
COINGECKO_BASE = "https://api.coingecko.com/api/v3"
ALTERNATIVE_BASE = "https://api.alternative.me"


def utc_now() -> str:
    return (
        datetime.now(timezone.utc)
        .isoformat(timespec="seconds")
        .replace("+00:00", "Z")
    )


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

            return (
                json.loads(payload.decode("utf-8")),
                utc_now()
            )

        except HTTPError as exc:
            last_error = f"HTTP_{exc.code}"

            if (
                exc.code not in (429, 500, 502, 503, 504)
                or attempt == 2
            ):
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


def make_metric(
    value: Any = None,
    unit: str | None = None,
    source: str | None = None,
    source_updated_at: str | None = None,
    status: str = "OK",
    error: str | None = None
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
        "fetched_at": utc_now(),
        "status": status,
        "error": error
    }


def unavailable_metric(
    source: str,
    error: str
) -> dict[str, Any]:

    return make_metric(
        source=source,
        status="UNAVAILABLE",
        error=error
    )


def fetch_global_market() -> dict[str, Any]:

    source = "CoinGecko API"

    keys = (
        "total_market_cap_usd",
        "total_volume_24h_usd",
        "btc_dominance_pct",
        "eth_dominance_pct",
        "active_cryptocurrencies",
        "markets_count"
    )

    try:
        data, fetched_at = http_json(
            f"{COINGECKO_BASE}/global"
        )

        market = data.get("data", {})

        if not isinstance(market, dict) or not market:
            raise ValueError("Missing global market payload")

        updated = market.get("updated_at")

        updated_at = None

        if updated:
            updated_at = (
                datetime.fromtimestamp(
                    int(updated),
                    timezone.utc
                )
                .isoformat(timespec="seconds")
                .replace("+00:00", "Z")
            )

        fields = {
            "total_market_cap_usd": (
                market.get("total_market_cap", {}).get("usd"),
                "USD"
            ),
            "total_volume_24h_usd": (
                market.get("total_volume", {}).get("usd"),
                "USD"
            ),
            "btc_dominance_pct": (
                market.get("market_cap_percentage", {}).get("btc"),
                "%"
            ),
            "eth_dominance_pct": (
                market.get("market_cap_percentage", {}).get("eth"),
                "%"
            ),
            "active_cryptocurrencies": (
                market.get("active_cryptocurrencies"),
                "count"
            ),
            "markets_count": (
                market.get("markets"),
                "count"
            )
        }

        result = {}

        for key, (value, unit) in fields.items():

            metric = make_metric(
                value,
                unit,
                source,
                updated_at or fetched_at
            )

            if metric["status"] == "OK" and updated_at:

                try:
                    age = (
                        datetime.now(timezone.utc)
                        - datetime.fromisoformat(
                            updated_at.replace("Z", "+00:00")
                        )
                    ).total_seconds()

                    if age > 7200:
                        metric["status"] = "STALE"

                except ValueError:
                    metric["status"] = "TIMESTAMP_UNKNOWN"

            result[key] = metric

        return result

    except Exception as exc:

        error = str(exc)[:240]

        return {
            key: unavailable_metric(source, error)
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
            raise ValueError("Fear & Greed value outside 0-100")

        timestamp = row.get("timestamp")
        updated = None

        if timestamp:
            updated = (
                datetime.fromtimestamp(
                    int(timestamp),
                    timezone.utc
                )
                .isoformat(timespec="seconds")
                .replace("+00:00", "Z")
            )

        age = None

        if updated:
            age = (
                datetime.now(timezone.utc)
                - datetime.fromisoformat(
                    updated.replace("Z", "+00:00")
                )
            ).total_seconds()

        if age is None:
            status = "TIMESTAMP_UNKNOWN"
        elif age > 48 * 3600:
            status = "STALE"
        else:
            status = "OK"

        return {
            "value": value,
            "classification": str(
                row.get("value_classification", "Unknown")
            ),
            "unit": "/100",
            "source": source,
            "source_updated_at": updated,
            "fetched_at": fetched_at,
            "status": status,
            "error": None
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
            "error": str(exc)[:240]
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

    seed = sum(values[:period]) / period

    result[period - 1] = seed

    multiplier = 2 / (period + 1)
    previous = seed

    for index in range(period, len(values)):

        previous = (
            (values[index] - previous) * multiplier
            + previous
        )

        result[index] = previous

    return result


def rsi(
    values: list[float],
    period: int = 14
) -> float | None:

    if len(values) <= period:
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

    avg_gain = sum(gains[:period]) / period
    avg_loss = sum(losses[:period]) / period

    for index in range(period, len(gains)):

        avg_gain = (
            avg_gain * (period - 1) + gains[index]
        ) / period

        avg_loss = (
            avg_loss * (period - 1) + losses[index]
        ) / period

    if avg_loss == 0:
        return 100.0 if avg_gain > 0 else 50.0

    rs = avg_gain / avg_loss

    return 100 - (100 / (1 + rs))


def calculate_indicators(
    candles: list[dict[str, float]]
) -> dict[str, Any]:

    closes = [c["close"] for c in candles]
    highs = [c["high"] for c in candles]
    lows = [c["low"] for c in candles]
    volumes = [c["volume"] for c in candles]

    ema20_series = ema_series(closes, 20)
    ema50_series = ema_series(closes, 50)

    ema12 = ema_series(closes, 12)
    ema26 = ema_series(closes, 26)

    macd_line = [
        None if a is None or b is None else a - b
        for a, b in zip(ema12, ema26)
    ]

    valid_macd = [
        value
        for value in macd_line
        if value is not None
    ]

    signal_series = (
        ema_series(valid_macd, 9)
        if valid_macd
        else []
    )

    macd_value = (
        valid_macd[-1]
        if valid_macd
        else None
    )

    macd_signal = (
        signal_series[-1]
        if signal_series
        else None
    )

    bb_period = closes[-20:]
    bb_mid = sma(closes, 20)

    bb_std = None

    if bb_mid is not None:
        bb_std = math.sqrt(
            sum(
                (value - bb_mid) ** 2
                for value in bb_period
            ) / 20
        )

    latest_volume = volumes[-1]
    avg_volume20 = sma(volumes, 20)

    return {
        "ma20": make_metric(
            sma(closes, 20), "USD", "Binance Spot 1D candles"
        ),
        "ma50": make_metric(
            sma(closes, 50), "USD", "Binance Spot 1D candles"
        ),
        "ma200": make_metric(
            sma(closes, 200), "USD", "Binance Spot 1D candles"
        ),
        "ema20": make_metric(
            ema20_series[-1], "USD", "Binance Spot 1D candles"
        ),
        "ema50": make_metric(
            ema50_series[-1], "USD", "Binance Spot 1D candles"
        ),
        "rsi14": make_metric(
            rsi(closes, 14), "index", "Binance Spot 1D candles"
        ),
        "macd": make_metric(
            macd_value, "USD", "Binance Spot 1D candles"
        ),
        "macd_signal": make_metric(
            macd_signal, "USD", "Binance Spot 1D candles"
        ),
        "macd_histogram": make_metric(
            macd_value - macd_signal
            if macd_value is not None and macd_signal is not None
            else None,
            "USD",
            "Binance Spot 1D candles"
        ),
        "bollinger_upper": make_metric(
            bb_mid + 2 * bb_std
            if bb_mid is not None and bb_std is not None
            else None,
            "USD",
            "Binance Spot 1D candles"
        ),
        "bollinger_middle": make_metric(
            bb_mid, "USD", "Binance Spot 1D candles"
        ),
        "bollinger_lower": make_metric(
            bb_mid - 2 * bb_std
            if bb_mid is not None and bb_std is not None
            else None,
            "USD",
            "Binance Spot 1D candles"
        ),
        "volume_24h_base": make_metric(
            latest_volume, "base asset", "Binance Spot 1D candles"
        ),
        "volume_sma20_base": make_metric(
            avg_volume20, "base asset", "Binance Spot 1D candles"
        ),
        "volume_ratio_20d": make_metric(
            latest_volume / avg_volume20
            if latest_volume is not None and avg_volume20
            else None,
            "x",
            "Binance Spot 1D candles"
        ),
        "support_20d": make_metric(
            min(lows[-20:]) if len(lows) >= 20 else None,
            "USD",
            "Binance Spot 1D candles"
        ),
        "resistance_20d": make_metric(
            max(highs[-20:]) if len(highs) >= 20 else None,
            "USD",
            "Binance Spot 1D candles"
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

    try:
        data, fetched_at = http_json(
            f"{BINANCE_BASE}/api/v3/klines",
            {
                "symbol": f"{symbol}USDT",
                "interval": "1d",
                "limit": 250
            }
        )

        if not isinstance(data, list) or len(data) < 200:
            raise ValueError("Insufficient daily candle history")

        candles = []

        for row in data:

            if not isinstance(row, list) or len(row) < 7:
                continue

            values = [
                finite_number(row[i])
                for i in (1, 2, 3, 4, 5)
            ]

            if any(value is None for value in values):
                continue

            candles.append({
                "open": values[0],
                "high": values[1],
                "low": values[2],
                "close": values[3],
                "volume": values[4],
                "open_time": int(row[0]),
                "close_time": int(row[6])
            })

        if len(candles) < 200:
            raise ValueError("Not enough valid candles")

        latest_close_time = candles[-1]["close_time"]

        latest_closed = datetime.fromtimestamp(
            latest_close_time / 1000,
            timezone.utc
        )

        age = (
            datetime.now(timezone.utc) - latest_closed
        ).total_seconds()

        status = "STALE" if age > 36 * 3600 else "OK"

        indicators = calculate_indicators(candles)

        updated_at = (
            latest_closed
            .isoformat(timespec="seconds")
            .replace("+00:00", "Z")
        )

        for metric in indicators.values():

            metric["source_updated_at"] = updated_at
            metric["fetched_at"] = fetched_at

            if metric["status"] == "OK":
                metric["status"] = status

        result.update({
            "price_usdt": make_metric(
                candles[-1]["close"],
                "USDT",
                source,
                updated_at,
                status
            ),
            "candle_interval": "1d",
            "candle_count": len(candles),
            "last_closed_candle_at": updated_at,
            "indicators": indicators
        })

    except Exception as exc:

        error = str(exc)[:240]

        indicator_names = (
            "ma20", "ma50", "ma200",
            "ema20", "ema50", "rsi14",
            "macd", "macd_signal", "macd_histogram",
            "bollinger_upper", "bollinger_middle",
            "bollinger_lower", "volume_24h_base",
            "volume_sma20_base", "volume_ratio_20d",
            "support_20d", "resistance_20d"
        )

        result.update({
            "price_usdt": unavailable_metric(source, error),
            "candle_interval": "1d",
            "candle_count": 0,
            "last_closed_candle_at": None,
            "indicators": {
                key: unavailable_metric(source, error)
                for key in indicator_names
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
            timestamp = item.get("last_updated_at")
            updated = None

            if timestamp:
                updated = (
                    datetime.fromtimestamp(
                        int(timestamp),
                        timezone.utc
                    )
                    .isoformat(timespec="seconds")
                    .replace("+00:00", "Z")
                )

            if not updated:
                status = "TIMESTAMP_UNKNOWN"
            else:
                age = (
                    datetime.now(timezone.utc)
                    - datetime.fromisoformat(
                        updated.replace("Z", "+00:00")
                    )
                ).total_seconds()

                status = "STALE" if age > 1800 else "OK"

            result[coin_id] = {
                "price_usd": make_metric(
                    item.get("usd"),
                    "USD",
                    source,
                    updated,
                    status
                ),
                "change_24h_pct": make_metric(
                    item.get("usd_24h_change"),
                    "%",
                    source,
                    updated,
                    status
                ),
                "source_updated_at": updated,
                "fetched_at": fetched_at
            }

        return result

    except Exception as exc:

        error = str(exc)[:240]

        return {
            coin: {
                "price_usd": unavailable_metric(source, error),
                "change_24h_pct": unavailable_metric(source, error),
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

        os.replace(temp_name, path)

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
        "update_mode": "on_workflow_run_not_realtime",
        "data_policy": (
            "Unavailable or stale values must not be treated "
            "as zero, neutral, or confirmed."
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

    for name, metric in payload["global_market"].items():
        print(
            f"global_market.{name}: "
            f"{metric['status']}"
        )

    print(
        f"fear_greed: "
        f"{payload['fear_greed']['status']}"
    )

    for asset, data in payload["technical"].items():
        print(
            f"technical.{asset}.price_usdt: "
            f"{data['price_usdt']['status']}"
        )

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
