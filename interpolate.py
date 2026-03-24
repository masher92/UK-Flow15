import os
import argparse
import pandas as pd
from typing import Optional


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


def interpolate_by_qc(
    in_dir: str,
    station_id: str,
    qc_column: int,
    qc_flags: str,
    out_dir_data: str,
    out_log_csv: Optional[str] = None,
    round_decimals: Optional[int] = 3,
) -> pd.DataFrame:
    """
    Generic QC-driven interpolation for ONE station.

    Parameters (order fixed as requested)
    ------------------------------------
    in_dir : str
        Directory with input CSVs.
    station_id : str
        Station ID (without .csv).
    qc_column : int
        QC digit to inspect: 0 (X), 1 (Y), 2 (Z).
    qc_flags : str
        Digits to interpolate, e.g. '238', '7'.
    out_dir_data : str
        Directory to save cleaned CSV.
    out_log_csv : str | None
        Optional path to append interpolation log CSV.
    round_decimals : int | None
        Decimal places to round interpolated values; set <0 to skip.

    Returns
    -------
    pd.DataFrame
        Interpolation log (possibly empty) with columns:
        ['station', 'datetime', 'old_value', 'new_value'].
    """
    # --- Load ---
    path_in = os.path.join(in_dir, f"{station_id}.csv")
    if not os.path.isfile(path_in):
        raise FileNotFoundError(f"Missing station file: {path_in}")

    df = pd.read_csv(path_in, parse_dates=["datetime"], index_col="datetime")
    for col in ("value", "flag"):
        if col not in df.columns:
            raise KeyError(f"Required column '{col}' not found in {path_in}")

    # --- Clean rows where value is the literal 'NA' and ensure numeric ---
    df = remove_empty(df)
    df["value"] = pd.to_numeric(df["value"], errors="coerce")

    # --- Normalize QC flags & build selection mask ---
    flag_str = normalize_flag_to_3char(df["flag"])
    selection_mask = build_qc_mask(flag_str, qc_column=qc_column, qc_flags=qc_flags)

    # --- Build interpolation log (old values) ---
    interp_log = pd.DataFrame(columns=["station", "datetime", "old_value", "new_value"])
    if selection_mask.any():
        selected_pts = (
            df.loc[selection_mask, ["value"]]
            .rename(columns={"value": "old_value"})
            .reset_index()
        )

        # Prepare for interpolation
        df = df.sort_index()
        if not df.index.is_unique:
            # defensively collapse duplicates before time interpolation
            df = df.groupby(level=0).mean(numeric_only=True)

        # Null selected values and interpolate
        df.loc[selection_mask, "value"] = pd.NA
        df["value"] = df["value"].interpolate(method="time")

        # Round if requested
        if (round_decimals is not None) and (round_decimals >= 0):
            df["value"] = df["value"].round(round_decimals)

        # New values back into log
        selected_pts["new_value"] = selected_pts["datetime"].map(df["value"])
        selected_pts["station"] = station_id
        interp_log = selected_pts[["station", "datetime", "old_value", "new_value"]]

    # --- Save cleaned data ---
    os.makedirs(out_dir_data, exist_ok=True)
    path_out = os.path.join(out_dir_data, f"{station_id}.csv")
    df.to_csv(path_out)

    # --- Append interpolation log if requested ---
    if out_log_csv and not interp_log.empty:
        os.makedirs(os.path.dirname(out_log_csv) or ".", exist_ok=True)
        if os.path.exists(out_log_csv) and os.path.getsize(out_log_csv) > 0:
            interp_log.to_csv(out_log_csv, mode="a", header=False, index=False)
        else:
            interp_log.to_csv(out_log_csv, index=False)

    return interp_log


def main():
    parser = argparse.ArgumentParser(
        description="Generic QC-driven interpolation for one or more stations (processed sequentially)."
    )

    # >>> ORDER OF ARGUMENTS (as requested) <<<
    parser.add_argument("--in_dir", required=True, help="Directory with input CSVs")
    parser.add_argument(
        "--station_id",
        required=True,
        nargs="+",
        help="One or more station IDs (without .csv). Space- and/or comma-separated, e.g. '026017 042006' or '026017,042006'.",
    )
    parser.add_argument("--qc_column", type=int, required=True, help="QC digit to inspect: 0 (X), 1 (Y), 2 (Z).")
    parser.add_argument("--qc_flags", type=str, required=True, help="Digits to interpolate, e.g. '238', '7'.")
    parser.add_argument("--out_dir_data", required=True, help="Directory to save cleaned CSVs")
    parser.add_argument("--out_log_csv", default=None, help="Optional path to append a combined interpolation log CSV")

    # Optional extras at the end
    parser.add_argument("--round_decimals", type=int, default=3, help="Decimal places to round interpolated values. Use -1 to skip.")

    args = parser.parse_args()

    # Normalize station IDs (support comma-separated entries too)
    station_ids = []
    for item in args.station_id:
        station_ids.extend([s.strip() for s in str(item).split(",") if s.strip()])

    # Normalize rounding option
    rd = None if (args.round_decimals is not None and args.round_decimals < 0) else args.round_decimals

    total_rows = 0
    for sid in station_ids:
        try:
            log = interpolate_by_qc(
                in_dir=args.in_dir,
                station_id=sid,
                qc_column=args.qc_column,
                qc_flags=args.qc_flags,
                out_dir_data=args.out_dir_data,
                out_log_csv=args.out_log_csv,   # shared log across stations (if provided)
                round_decimals=rd,
            )
            print(f"[{sid}] interpolated {len(log)} QC-matched rows.")
            total_rows += len(log)
        except Exception as e:
            print(f"[{sid}] ❌ Error: {e}")

    print(f"→ Done. Total interpolated rows across {len(station_ids)} station(s): {total_rows}.")


if __name__ == "__main__":
    main()