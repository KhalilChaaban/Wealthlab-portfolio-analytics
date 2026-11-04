"""Explicit-source market data, checksummed caching, and strict quality checks.

Demo prices are synthetic total-return indices carrying familiar ETF labels.
They are not ETF observations. Yahoo adjusted closes are total-return proxies;
cash distributions must NOT be added to those returns a second time.
"""

from dataclasses import dataclass
from datetime import datetime, timezone
from hashlib import sha256
from io import StringIO
from pathlib import Path
import json
import logging
import os
import time

import numpy as np
import pandas as pd

from .config import ResearchConfig, ensure_directory

LOGGER = logging.getLogger(__name__)


class DataError(RuntimeError):
    """A provider or cache failed; no fabricated market-data fallback is allowed."""


class DataQualityError(ValueError):
    """Data cannot safely enter the accounting engine."""


@dataclass
class MarketData:
    prices: pd.DataFrame
    manifest: dict


def atomic_text(path: Path, text: str) -> None:
    """Replace a single artifact atomically on the same filesystem."""
    ensure_directory(path.parent)
    temporary = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    try:
        temporary.write_text(text, encoding="utf-8")
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def _request_spec(config: ResearchConfig) -> dict:
    return {
        "schema": 1, "source": config.source, "start": config.start, "end": config.end,
        "tickers": list(config.weights), "field": "adjusted_close_total_return_proxy",
        "demo_seed": config.seed if config.source == "demo" else None,
        "demo_generator": "factor-lognormal-v1" if config.source == "demo" else None,
        "demo_periods_per_year": config.periods_per_year if config.source == "demo" else None,
    }


def _demo_prices(config: ResearchConfig) -> pd.DataFrame:
    dates = pd.bdate_range(config.start, pd.Timestamp(config.end) - pd.Timedelta(days=1))
    if len(dates) < config.min_observations:
        raise DataError("The demo date range has too few observations; extend the requested window.")
    tickers = list(config.weights)
    rng = np.random.default_rng(config.seed)
    # Four common economic drivers plus idiosyncratic shocks ensure a PSD model.
    loadings = {
        "SPY": [0.17, 0.00, 0.00, 0.00], "VEA": [0.15, 0.00, 0.07, 0.00],
        "VWO": [0.16, 0.00, 0.12, 0.00], "AGG": [-0.01, 0.05, 0.00, 0.00],
        "TIP": [0.00, 0.055, 0.00, 0.025], "GLD": [-0.01, 0.01, 0.02, 0.14],
        "VNQ": [0.13, 0.035, 0.00, 0.025], "BIL": [0.00, 0.002, 0.00, 0.00],
    }
    mus = {"SPY": .08, "VEA": .065, "VWO": .07, "AGG": .03,
           "TIP": .035, "GLD": .04, "VNQ": .065, "BIL": .02}
    if set(tickers) - set(loadings):
        raise DataError("Demo supports the documented eight ETFs; use Yahoo for other tickers.")
    matrix = np.array([loadings[t] for t in tickers])
    factors = rng.standard_normal((len(dates) - 1, 4))
    noise_scale = np.array([.002 if t == "BIL" else .025 for t in tickers])
    shocks = (factors @ matrix.T + rng.standard_normal((len(dates)-1, len(tickers)))
              * noise_scale) / np.sqrt(config.periods_per_year)
    variance = np.sum(matrix ** 2, axis=1) + noise_scale ** 2
    drift = (np.log1p([mus[t] for t in tickers]) - .5 * variance) / config.periods_per_year
    log_paths = np.vstack([np.zeros(len(tickers)), np.cumsum(drift + shocks, axis=0)])
    return pd.DataFrame(100 * np.exp(log_paths), index=dates, columns=tickers).rename_axis("date")


def extract_yahoo_adjusted_close(raw: pd.DataFrame, tickers: list[str]) -> pd.DataFrame:
    """Handle both common yfinance MultiIndex layouts and the single-ticker case."""
    if raw is None or raw.empty:
        raise DataError("Yahoo returned no data. Check dates, connectivity, and provider limits.")
    if isinstance(raw.columns, pd.MultiIndex):
        selected = None
        for level in range(raw.columns.nlevels):
            if "Adj Close" in raw.columns.get_level_values(level):
                selected = raw.xs("Adj Close", axis=1, level=level)
                break
        if selected is None:
            raise DataError("Adjusted Close is absent; refusing to substitute unadjusted prices.")
    elif "Adj Close" in raw.columns and len(tickers) == 1:
        selected = raw[["Adj Close"]].rename(columns={"Adj Close": tickers[0]})
    else:
        raise DataError("Unexpected Yahoo schema; adjusted-close data is required.")
    missing = set(tickers) - set(selected.columns)
    if missing:
        raise DataError(f"Missing tickers in Yahoo response: {sorted(missing)}")
    return selected.reindex(columns=tickers).rename_axis("date")


def load_prices(config: ResearchConfig, cache_dir: str | Path, refresh: bool = False) -> MarketData:
    """Load an immutable request snapshot or explicitly fetch a new one.

    Cache identity includes source, dates, tickers, and adjustment settings.
    A checksum mismatch is an error, not an invitation to overwrite evidence.
    """
    spec = _request_spec(config)
    cache = ensure_directory(cache_dir)
    key = sha256(json.dumps(spec, sort_keys=True).encode()).hexdigest()[:20]
    csv_path, meta_path = cache / f"{key}.csv", cache / f"{key}.json"
    if not refresh and csv_path.exists() and meta_path.exists():
        metadata = json.loads(meta_path.read_text())
        payload = csv_path.read_bytes()
        if metadata.get("request") != spec or sha256(payload).hexdigest() != metadata.get("sha256"):
            raise DataError("Cache integrity check failed. Inspect it, then explicitly refresh.")
        frame = pd.read_csv(StringIO(payload.decode()), index_col=0, parse_dates=True)
        return MarketData(frame, {**metadata, "cache_hit": True})
    if config.source == "demo":
        frame = _demo_prices(config)
        provider = "SYNTHETIC DEMO — NOT MARKET DATA"
    else:
        try:
            import yfinance as yf
        except ImportError as exc:
            raise DataError("Install requirements-live.txt before selecting source='yahoo'.") from exc
        failure = None
        for attempt in range(3):
            try:
                raw = yf.download(
                    list(config.weights), start=config.start, end=config.end,
                    auto_adjust=False, back_adjust=False, repair=False, actions=True,
                    progress=False, threads=False, timeout=20, group_by="column",
                    keepna=True, interval="1d",
                )
                frame = extract_yahoo_adjusted_close(raw, list(config.weights))
                if frame.notna().sum().min() < config.min_observations:
                    raise DataError("At least one requested ticker has insufficient observations.")
                break
            except Exception as exc:
                failure = exc
                LOGGER.warning("Yahoo attempt %s/3 failed (%s).", attempt + 1, type(exc).__name__)
                if attempt < 2:
                    time.sleep(2 ** attempt)
        else:
            raise DataError("Yahoo failed after three attempts; demo mode was not substituted.") from failure
        provider = f"Yahoo Finance via yfinance {yf.__version__}; personal research use"
    payload = frame.to_csv(float_format="%.12g")
    metadata = {
        "request": spec, "provider": provider,
        "retrieved_at_utc": datetime.now(timezone.utc).isoformat(),
        "sha256": sha256(payload.encode()).hexdigest(), "rows": len(frame),
        "synthetic": config.source == "demo",
    }
    atomic_text(csv_path, payload)
    atomic_text(meta_path, json.dumps(metadata, indent=2))
    # Round-trip the exact cached bytes so fresh and cached runs use identical inputs.
    frame = pd.read_csv(StringIO(payload), index_col=0, parse_dates=True)
    return MarketData(frame, {**metadata, "cache_hit": False})


def clean_prices(raw: pd.DataFrame, config: ResearchConfig) -> tuple[pd.DataFrame, dict]:
    """Sort and align data; never forward-fill, backfill, clip returns, or drop assets."""
    if raw.empty or raw.columns.has_duplicates:
        raise DataQualityError("Prices are empty or contain duplicate asset columns.")
    required = list(config.weights)
    if set(required) - set(raw.columns):
        raise DataQualityError("A required asset is absent.")
    frame = raw.loc[:, required].copy()
    frame.index = pd.to_datetime(frame.index, errors="raise")
    if frame.index.tz is not None:
        frame.index = frame.index.tz_localize(None)
    if frame.index.hasnans or not frame.index.equals(frame.index.normalize()):
        raise DataQualityError("Daily data requires valid date-only timestamps.")
    frame = frame.sort_index()
    duplicate_count = int(frame.index.duplicated().sum())
    if duplicate_count:
        for _, group in frame.loc[frame.index.duplicated(keep=False)].groupby(level=0):
            if (group.nunique(dropna=False) > 1).any():
                raise DataQualityError("Conflicting duplicate-date prices must be resolved upstream.")
        frame = frame.loc[~frame.index.duplicated(keep="first")]
    frame = frame.apply(pd.to_numeric, errors="raise")
    if np.isinf(frame.to_numpy()).any() or (frame <= 0).any().any():
        raise DataQualityError("Prices must be finite, strictly positive, or explicitly missing.")
    starts, ends = frame.apply(pd.Series.first_valid_index), frame.apply(pd.Series.last_valid_index)
    if starts.isna().any() or ends.isna().any():
        raise DataQualityError("An asset has no valid prices.")
    lower = max(pd.Timestamp(config.start), max(starts))
    upper = min(pd.Timestamp(config.end) - pd.Timedelta(days=1), min(ends))
    aligned = frame.loc[lower:upper].copy()
    missing = aligned.isna().sum()
    if missing.any():
        raise DataQualityError(f"Interior missing values found: {missing[missing > 0].to_dict()}. No fill applied.")
    if len(aligned) < config.min_observations:
        raise DataQualityError(f"Need {config.min_observations} common observations; found {len(aligned)}.")
    largest_gap = int(aligned.index.to_series().diff().dt.days.max())
    if largest_gap > config.max_calendar_gap_days:
        raise DataQualityError(f"A {largest_gap}-day gap requires investigation before analysis.")
    if (pd.Timestamp(config.end) - aligned.index[-1]).days > config.max_calendar_gap_days:
        raise DataQualityError("Data stops substantially before the requested end date.")
    if (aligned.index[0] - pd.Timestamp(config.start)).days > config.max_calendar_gap_days:
        raise DataQualityError("Common inception is too late; explicitly choose a later start date.")
    returns = aligned.pct_change(fill_method=None).iloc[1:]
    report = {
        "input_rows": len(raw), "retained_rows": len(aligned),
        "identical_duplicates_removed": duplicate_count,
        "rows_outside_common_range": len(frame) - len(aligned),
        "first_observation": aligned.index[0].date().isoformat(),
        "last_observation": aligned.index[-1].date().isoformat(),
        "largest_calendar_gap_days": largest_gap,
        "absolute_daily_moves_above_20pct": int((returns.abs() > .20).sum().sum()),
        "price_policy": "adjusted total-return proxy; no filling or clipping",
        "calendar_limit": "No exchange-calendar completeness guarantee; gap checks are heuristic.",
    }
    return aligned.rename_axis("date"), report


def risk_free_returns(dates: pd.DatetimeIndex, config: ResearchConfig,
                      cache_dir: str | Path, refresh: bool = False) -> tuple[pd.Series, dict]:
    """Calendar-day accrual using a constant rate or lagged FRED DGS3MO proxy.

    FRED observations are lagged by at least one calendar day, with a maximum
    seven-day age. This is a yield proxy, not an investable T-bill backtest or
    a full vintage reconstruction. API keys never enter cache keys or logs.
    """
    gaps = dates.to_series().diff().dt.days.fillna(0).to_numpy()
    if config.risk_free_source == "constant":
        values = np.full(len(dates), config.annual_risk_free_rate)
        metadata = {"source": "explicit constant effective-annual assumption",
                    "rate": config.annual_risk_free_rate}
    else:
        start = (dates[0] - pd.Timedelta(days=14)).date().isoformat()
        end = dates[-1].date().isoformat()
        cache = ensure_directory(cache_dir)
        key = sha256(f"fred-DGS3MO-{start}-{end}-v1".encode()).hexdigest()[:20]
        path = cache / f"fred-{key}.json"
        if path.exists() and not refresh:
            stored = json.loads(path.read_text())
            payload = stored["payload"]
            if sha256(json.dumps(payload, sort_keys=True).encode()).hexdigest() != stored["sha256"]:
                raise DataError("FRED cache checksum failed.")
        else:
            api_key = os.getenv("FRED_API_KEY")
            if not api_key:
                raise DataError("Set FRED_API_KEY before selecting risk_free_source='fred'.")
            try:
                import requests
            except ImportError as exc:
                raise DataError("Install requirements-live.txt to use FRED.") from exc
            from requests.adapters import HTTPAdapter
            from urllib3.util.retry import Retry
            session = requests.Session()
            session.mount("https://", HTTPAdapter(max_retries=Retry(
                total=2, backoff_factor=.5, status_forcelist=[429, 500, 502, 503, 504],
                allowed_methods=["GET"], respect_retry_after_header=False)))
            try:
                response = session.get(
                    "https://api.stlouisfed.org/fred/series/observations",
                    params={"series_id": "DGS3MO", "api_key": api_key, "file_type": "json",
                            "observation_start": start, "observation_end": end}, timeout=(10, 30))
                response.raise_for_status()
                payload = response.json()
                if "observations" not in payload or not payload["observations"]:
                    raise ValueError("No FRED observations returned.")
            except Exception:
                # requests exceptions may contain the credential-bearing URL.
                raise DataError("FRED request failed. Verify the key, connection, and endpoint.") from None
            finally:
                session.close()
            stored = {"payload": payload, "retrieved_at_utc": datetime.now(timezone.utc).isoformat(),
                      "sha256": sha256(json.dumps(payload, sort_keys=True).encode()).hexdigest()}
            atomic_text(path, json.dumps(stored))
        observations = pd.DataFrame(payload["observations"])
        observations["date"] = pd.to_datetime(observations["date"])
        observations["rate"] = pd.to_numeric(observations["value"], errors="coerce") / 100
        observations = observations.dropna(subset=["rate"]).sort_values("date")
        queries = pd.DataFrame({"date": dates - pd.Timedelta(days=1)})
        observed = observations[["date", "rate"]].rename(columns={"date": "observed_date"})
        matched = pd.merge_asof(queries, observed, left_on="date", right_on="observed_date",
                                # Queries are already one day before the trading date:
                                # six further days permit an actual maximum age of seven.
                                direction="backward", tolerance=pd.Timedelta(days=6))
        if matched["rate"].isna().any():
            raise DataError("Insufficient lagged FRED yields; no rate fallback was substituted.")
        values = matched["rate"].to_numpy()
        if not np.isfinite(values).all() or (values <= -1).any():
            raise DataError("FRED yields are outside supported accrual bounds.")
        metadata = {"source": "FRED DGS3MO; lagged yield proxy, latest retrieved vintage",
                    "retrieved_at_utc": stored["retrieved_at_utc"], "sha256": stored["sha256"],
                    "convention": "yield/100 treated as effective annual, ACT/365.25; approximation"}
    return pd.Series(np.expm1(np.log1p(values) * gaps / 365.25), index=dates,
                     name="risk_free_return"), metadata
