import os
import re
import argparse
import pandas as pd
from typing import Iterable, Optional, List


def _normalize_station_ids(station_id: Optional[object]) -> List[str]:
    """
    Accepts None, a single string ('042006' or '042006,026017'), or an iterable.
    Returns a list of zero-padded 6-char station ids.
    """
    def _norm_one(s: str) -> str:
        s = s.strip()
        if re.fullmatch(r"\d+", s):
            return s.zfill(6)
        return s

    if station_id is None:
        return []
    if isinstance(station_id, str):
        parts = re.split(r"[,\s]+", station_id.strip())
        return [_norm_one(p) for p in parts if p]
    if isinstance(station_id, Iterable):
        out = []
        for item in station_id:
            if item is None:
                continue
            if isinstance(item, str):
                out.extend([_norm_one(p) for p in re.split(r"[,\s]+", item.strip()) if p])
            else:
                out.append(_norm_one(str(item)))
        return [p for p in out if p]
    return [_norm_one(str(station_id))]


def _coerce_real_to_bool(series: pd.Series) -> pd.Series:
    """Coerce 'real' to boolean from strings like 'False','TRUE','0','1','no','yes'."""
    mapping = {
        'true': True, 't': True, '1': True, 'yes': True, 'y': True,
        'false': False, 'f': False, '0': False, 'no': False, 'n': False
    }
    s = series.astype(str).str.strip().str.lower()
    return s.map(mapping).fillna(False)


def prune_false(
    in_dir: str,
    station_id: Optional[object],
    visual_log_csv: str,
    pad_timesteps: int,
    out_dir_data: str,
) -> None:
    """
    Remove data for ranges labeled as FALSE in the visual review log,
    expanding each window by a number of index timesteps on both sides.

    Parameters (ORDER AS REQUESTED)
    --------------------------------
    in_dir : str
        Directory where input stations are located.
    station_id : str | Iterable[str] | None
        Stations to be examined for artefacts. Optional; if omitted, all stations in the log are used.
    visual_log_csv : str
        Output of the visual review of data (CSV with columns: station,start,end,real).
    pad_timesteps : int
        Number of timesteps before and after the truncation to be removed in addition to the artefact flagged.
    out_dir_data : str
        Location for saving the station with removed False values.
    """
    if not os.path.isfile(visual_log_csv):
        raise FileNotFoundError(f"Labels file not found: {visual_log_csv}")

    # Read labels, preserve leading zeros for station
    df_chunks = pd.read_csv(
        visual_log_csv,
        parse_dates=["start", "end"],
        dtype={"station": str},
    )

    for col in ("station", "start", "end", "real"):
        if col not in df_chunks.columns:
            raise KeyError(f"Labels file must contain column: '{col}'")

    # Normalize station ids in log (zfill 6 if numeric-like)
    df_chunks["station"] = df_chunks["station"].astype(str).str.strip()
    df_chunks["station"] = df_chunks["station"].where(
        ~df_chunks["station"].str.fullmatch(r"\d+"),
        df_chunks["station"].str.zfill(6),
    )

    # Coerce 'real' to boolean and filter FALSE only
    df_chunks["real_bool"] = _coerce_real_to_bool(df_chunks["real"])
    df_false = df_chunks[df_chunks["real_bool"] == False].copy()

    # Optional: filter to provided station_ids
    stations = _normalize_station_ids(station_id)
    if stations:
        df_false = df_false[df_false["station"].isin(stations)]

    if df_false.empty:
        print("ℹ️ No FALSE-labeled ranges (after station filter, if any). Nothing to prune.")
        return

    os.makedirs(out_dir_data, exist_ok=True)
    pad = max(0, int(pad_timesteps))

    for st, group in df_false.groupby("station"):
        in_path  = os.path.join(in_dir, f"{st}.csv")
        out_path = os.path.join(out_dir_data, f"{st}.csv")

        if not os.path.isfile(in_path):
            print(f"⚠️ Missing file for station {st}: {in_path}")
            continue

        df = pd.read_csv(
            in_path,
            parse_dates=["datetime"],
            index_col="datetime",
            dtype={"flag": str},
        )

        if df.empty or not isinstance(df.index, pd.DatetimeIndex):
            print(f"⚠️ Skipping station {st}: empty or invalid datetime index.")
            continue

        # Ensure strictly increasing index for positional padding
        df = df.sort_index()
        idx = df.index
        n = len(idx)
        mask_remove = pd.Series(False, index=idx)

        # For each FALSE chunk, mark [start, end] and expand by pad index steps
        for _, row in group.iterrows():
            left_pos = idx.searchsorted(row["start"], side="left")
            right_pos = idx.searchsorted(row["end"], side="right") - 1
            if right_pos < left_pos:
                continue
            left_pos = max(0, left_pos - pad)
            right_pos = min(n - 1, right_pos + pad)
            mask_remove.iloc[left_pos:right_pos + 1] = True

        pruned_count = int(mask_remove.sum())
        df_pruned = df.loc[~mask_remove]
        df_pruned.to_csv(out_path)
        print(f"✔ Station {st}: pruned {pruned_count} rows (pad_timesteps={pad}) → {out_path}")


def main():
    parser = argparse.ArgumentParser(
        description="Prune FALSE-labeled ranges (from visual review) with index-step padding."
    )

    # >>> ARG ORDER (as requested) <<<
    parser.add_argument("--in_dir", required=True,
                        help="Directory where input stations are located")
    parser.add_argument("--station_id", required=False, nargs="+",
                        help="Stations to be examined for artefacts (IDs without .csv). Space- and/or comma-separated. Optional.")
    parser.add_argument("--visual_log_csv", required=True,
                        help="Output of the visual review of data")
    parser.add_argument("--pad_timesteps", type=int, default=0,
                        help="Number of timesteps, before and after the truncation to be removed in addition to the artefact flagged")
    parser.add_argument("--out_dir_data", required=True,
                        help="Location for saving the station with removed False values")

    args = parser.parse_args()

    station_ids = None
    if args.station_id is not None:
        station_ids = _normalize_station_ids(args.station_id)

    prune_false(
        in_dir=args.in_dir,
        station_id=station_ids,
        visual_log_csv=args.visual_log_csv,
        pad_timesteps=args.pad_timesteps,
        out_dir_data=args.out_dir_data,
    )


if __name__ == "__main__":
    main()