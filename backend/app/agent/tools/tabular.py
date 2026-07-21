import math
from pathlib import Path
from typing import Any  # noqa: UP035 -- pandas values are intentionally heterogeneous

import pandas as pd
import pyarrow.parquet as parquet

SUPPORTED_SUFFIXES = {".csv", ".json", ".jsonl", ".parquet", ".xlsx", ".xls", ".txt"}


def file_format(file_name: str) -> str:
    suffix = Path(file_name).suffix.lower()
    if suffix not in SUPPORTED_SUFFIXES:
        raise ValueError(f"unsupported file type: {suffix or 'unknown'}")
    return suffix.removeprefix(".")


def read_dataframe(path: Path, file_name: str, max_rows: int) -> pd.DataFrame:
    suffix = Path(file_name).suffix.lower()
    if suffix == ".csv":
        frame = _read_csv(path, max_rows)
    elif suffix in {".json", ".jsonl"}:
        frame = pd.read_json(path, lines=suffix == ".jsonl")
    elif suffix == ".parquet":
        if parquet.ParquetFile(path).metadata.num_rows > max_rows:
            raise ValueError(f"row limit exceeded: {max_rows}")
        frame = pd.read_parquet(path)
    elif suffix in {".xlsx", ".xls"}:
        frame = pd.read_excel(path, nrows=max_rows + 1)
    elif suffix == ".txt":
        try:
            frame = pd.read_csv(path, sep=None, engine="python", nrows=max_rows + 1)
        except Exception:
            lines = path.read_text(encoding="utf-8-sig").splitlines()
            frame = pd.DataFrame({"text": lines})
    else:
        raise ValueError(f"unsupported file type: {suffix or 'unknown'}")
    if len(frame.index) > max_rows:
        raise ValueError(f"row limit exceeded: {max_rows}")
    frame.columns = [str(column).strip() for column in frame.columns]
    return frame


def _read_csv(path: Path, max_rows: int) -> pd.DataFrame:
    last_error: Exception | None = None
    for encoding in ("utf-8-sig", "utf-8", "gb18030"):
        try:
            return pd.read_csv(path, encoding=encoding, nrows=max_rows + 1)
        except UnicodeDecodeError as exc:
            last_error = exc
    if last_error:
        raise last_error
    raise ValueError("unable to read CSV")


def json_safe(value: Any) -> Any:
    if isinstance(value, dict):
        return {str(key): json_safe(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [json_safe(item) for item in value]
    if value is None:
        return None
    try:
        if pd.isna(value):
            return None
    except (TypeError, ValueError):
        pass
    if hasattr(value, "item"):
        value = value.item()
    if isinstance(value, float) and (math.isnan(value) or math.isinf(value)):
        return None
    if isinstance(value, pd.Timestamp):
        return value.isoformat()
    return value


def dataframe_preview(frame: pd.DataFrame, rows: int) -> list[dict[str, Any]]:
    return json_safe(frame.head(rows).to_dict(orient="records"))
