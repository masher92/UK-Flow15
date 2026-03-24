import os
import argparse
import pandas as pd
import matplotlib.pyplot as plt
from matplotlib.widgets import Button


def remove_empty(df: pd.DataFrame) -> pd.DataFrame:
    """
    Remove rows where the 'value' column equals the literal string 'NA' (case-insensitive).
    NOTE: This does NOT drop numeric NaNs or other blanks—only rows where value == 'NA' as a string.
    """
    if "value" not in df.columns:
        raise KeyError("Column 'value' not found in input data.")
    is_na_string = df["value"].astype(str).str.strip().str.upper() == "NA"
    return df.loc[~is_na_string].copy()


def build_qc_mask(flag_str_series: pd.Series, qc_column: int, qc_flags: str) -> pd.Series:
    """
    Build a boolean mask for a 3-character QC flag where:
      - qc_column is which character to check (0, 1, or 2)
      - qc_flags is a string of digits to match at that position, e.g. "7" or "12789"
    Assumes flags are already strings and length==3 (rows not matching length 3 are ignored).
    """
    if qc_column not in (0, 1, 2):
        raise ValueError("qc_column must be 0, 1, or 2 for a 3-character QC flag.")
    if not qc_flags or any(ch not in "0123456789" for ch in qc_flags):
        raise ValueError("qc_flags must be a non-empty string of digits 0–9, e.g. '7' or '12789'.")

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


def review_station_chunks(
    in_dir: str,
    station_id,
    qc_column: int = 2,
    qc_flags: str = "12789",
    out_log_csv: str = "visual_review_labels.csv",
):
    """
    Interactive QC-driven visual review for one or more stations.

    Parameters
    ----------
    in_dir : str
        Directory containing <station_id>.csv files.
    station_id : list[str] or str
        One or more station identifiers (without .csv extension).
    qc_column : int
        Which character of the 3-char flag to inspect: 0 -> X, 1 -> Y, 2 -> Z.
    qc_flags : str
        Digits (0–9) that should be considered a match at that position, e.g. "7" or "12789".
    out_log_csv : str
        Path to save labeled chunks across all stations.
    """
    # Normalize station_id to a flat list, supporting comma-separated and/or multiple args
    if isinstance(station_id, str):
        station_list = [x.strip() for x in station_id.split(",") if x.strip()]
    else:
        station_list = []
        for item in station_id:
            station_list.extend([x.strip() for x in str(item).split(",") if x.strip()])

    all_results = []

    for sid in station_list:
        path = os.path.join(in_dir, f"{sid}.csv")
        if not os.path.isfile(path):
            print(f"⚠️ Missing file for station {sid}: {path}")
            continue

        df = pd.read_csv(path, parse_dates=["datetime"], index_col="datetime")

        # Ensure required columns exist
        for col in ("value", "flag"):
            if col not in df.columns:
                print(f"⚠️ Column '{col}' not found in {path}; skipping station {sid}.")
                break
        else:
            # Remove rows where value == 'NA' (string)
            df = remove_empty(df)

            # Normalize flag to zero-padded 3-character strings (e.g., 0 -> '000', 60 -> '060')
            flag_str = pd.to_numeric(df["flag"], errors="coerce").fillna(0).astype(int).astype(str).str.zfill(3)

            # Infer timestep from the full series index
            expected_delta = infer_time_step(df.index)

            # Build QC mask on normalized flags
            mask = build_qc_mask(flag_str, qc_column=qc_column, qc_flags=qc_flags)
            times = df.index[mask].sort_values()

            if times.empty:
                print(
                    f"ℹ️ No QC flags matching column {qc_column} with digits '{qc_flags}' "
                    f"for station {sid}."
                )
                continue

            # Group into consecutive runs
            runs = group_consecutive_times(times, expected_delta)
            print(
                f"👉 Station {sid}: {len(runs)} chunk(s) to review "
                f"(qc_column={qc_column}, qc_flags='{qc_flags}', step={expected_delta})."
            )

            # Interactive labeling for each run
            for start, end in runs:
                window = df.loc[start - pd.Timedelta(days=1): end + pd.Timedelta(days=1), "value"]

                fig, ax = plt.subplots(figsize=(10, 4))
                ax.plot(window.index, window.values, lw=1)
                ax.axvspan(start, end, color="red", alpha=0.3, label="Chunk")
                ax.set_title(f"{sid} — {start:%Y-%m-%d %H:%M} to {end:%Y-%m-%d %H:%M}")
                ax.set_xlabel("Datetime")
                ax.set_ylabel("Value")
                ax.legend(loc="upper left")

                # Buttons
                ax_t = plt.axes([0.7, 0.01, 0.1, 0.06])
                ax_f = plt.axes([0.81, 0.01, 0.1, 0.06])
                btn_true = Button(ax_t, "True")
                btn_false = Button(ax_f, "False")

                def on_true(event, st=sid, s=start, e=end):
                    all_results.append(
                        {
                            "station": st,
                            "start": s,
                            "end": e,
                            "real": True,
                            "qc_column": qc_column,
                            "qc_flags": qc_flags,
                        }
                    )
                    plt.close(fig)

                def on_false(event, st=sid, s=start, e=end):
                    all_results.append(
                        {
                            "station": st,
                            "start": s,
                            "end": e,
                            "real": False,
                            "qc_column": qc_column,
                            "qc_flags": qc_flags,
                        }
                    )
                    plt.close(fig)

                btn_true.on_clicked(on_true)
                btn_false.on_clicked(on_false)

                plt.tight_layout()
                plt.show()

    # Ensure output folder exists and save all results together
    outdir = os.path.dirname(out_log_csv)
    if outdir and not os.path.exists(outdir):
        os.makedirs(outdir, exist_ok=True)

    pd.DataFrame(all_results).to_csv(out_log_csv, index=False)
    print(f"✅ Saved {len(all_results)} labeled chunks to {out_log_csv}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Interactively review QC chunks for one or more stations."
    )

    # >>> order & names as requested <<<
    parser.add_argument("--in_dir", required=True, help="Directory containing <station_id>.csv")
    parser.add_argument(
        "--station_id",
        required=True,
        nargs="+",
        help="One or more station IDs (without .csv). You can pass space- and/or comma-separated values.",
    )
    parser.add_argument(
        "--qc_column",
        type=int,
        default=2,
        help="Which digit of the 3-digit QC flag: 0 (X), 1 (Y), 2 (Z). Default=2.",
    )
    parser.add_argument(
        "--qc_flags",
        type=str,
        default="12789",
        help="Digits to match at that position, e.g. '7' or '12789'. Default='12789'.",
    )
    parser.add_argument("--out_log_csv", required=True, help="Path to save labeled chunks CSV")

    args = parser.parse_args()

    review_station_chunks(
        in_dir=args.in_dir,
        station_id=args.station_id,
        qc_column=args.qc_column,
        qc_flags=args.qc_flags,
        out_log_csv=args.out_log_csv,
    )