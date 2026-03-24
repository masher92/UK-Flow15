import pandas as pd

def remove_empty(df: pd.DataFrame) -> pd.DataFrame:
    """
    Remove rows where the 'value' column equals the literal string 'NA' (case-insensitive).
    Does not drop numeric NaNs or other blanks.
    """
    if "value" not in df.columns:
        raise KeyError("Column 'value' not found in input data.")
    is_na_string = df["value"].astype(str).str.strip().str.upper() == "NA"
    return df.loc[~is_na_string].copy()

def normalize_flag_to_3char(flag_series: pd.Series) -> pd.Series:
    """
    Normalize flag values to zero-padded 3-character strings:
      0   -> '000'
      60  -> '060'
      137 -> '137'
    Non-numeric or missing -> 0 -> '000'
    """
    nums = pd.to_numeric(flag_series, errors="coerce").fillna(0).astype(int)
    return nums.astype(str).str.zfill(3)


def build_qc_mask(flag_str_series: pd.Series, qc_column: int, qc_flags: str) -> pd.Series:
    """
    Return a boolean mask where the character at qc_column is in qc_flags.
      - qc_column: 0, 1, or 2 (X, Y, Z)
      - qc_flags:  string of digits, e.g. '238', '7', or '0123456789'
    """
    if qc_column not in (0, 1, 2):
        raise ValueError("qc_column must be 0, 1, or 2 for a 3-character QC flag.")
    if not qc_flags or any(ch not in "0123456789" for ch in qc_flags):
        raise ValueError("qc_flags must be a non-empty string of digits 0–9, e.g. '7' or '238'.")

    s = flag_str_series.astype(str)
    ok_len = s.str.len() == 3
    s_ok = s.where(ok_len, None)
    return ok_len & s_ok.str[qc_column].isin(list(qc_flags))

def infer_time_step(index: pd.DatetimeIndex) -> pd.Timedelta:
    """
    Infer the most common time step from a DateTimeIndex.
    Falls back to 15 minutes if inference fails.
    """
    if len(index) < 2:
        return pd.Timedelta(minutes=15)
    diffs = pd.Series(index.sort_values()).diff().dropna()
    if diffs.empty:
        return pd.Timedelta(minutes=15)
    return diffs.value_counts().idxmax()


def group_consecutive_times(times: pd.DatetimeIndex, expected_delta: pd.Timedelta):
    """
    Group sorted times into consecutive runs separated by expected_delta.
    Returns a list of (start, end) tuples.
    """
    times = pd.DatetimeIndex(times).sort_values()
    if len(times) == 0:
        return []

    runs = []
    run_start = times[0]
    prev = times[0]

    for t in times[1:]:
        if t - prev == expected_delta:
            prev = t
        else:
            runs.append((run_start, prev))
            run_start = t
            prev = t
    runs.append((run_start, prev))
    return runs

