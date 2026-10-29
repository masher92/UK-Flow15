import pandas as pd
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
import numpy as np
import math
from scipy.signal import find_peaks

def find_highest_unflagged_events(df, n=1, exclude=pd.Timedelta("5D"),
                                  start=None, end=None, min_value=None,
                                  value_col="value", flag_col="flagged_mask"):
    s = df[value_col].dropna()
    s = s[~df.loc[s.index, flag_col].fillna(False).astype(bool)]   # unflagged samples only
    s = s.loc[start:end]                                           # event window (None = open)
    s = s.sort_values(ascending=False)

    picked = []
    for t, val in s.items():
        if min_value is not None and val <= min_value:
            break                                                  # sorted, so nothing higher remains
        if all(abs(t - p) > exclude for p, _ in picked):           # one pick per event
            picked.append((t, val))
            if len(picked) >= n:
                break
    return pd.DataFrame(picked, columns=["time", "value"])


def plot_run_vs_highest_event(df, runs, k, rank=0, pad=pd.Timedelta("5D"),
                              exclude=pd.Timedelta("5D"),
                              event_start=None, event_end=None,
                              above_target=True):
    r = runs.loc[k]

    # Flagged run window
    t0, t1 = r["start"] - pad, r["end"] + pad
    window = df.loc[t0:t1]
    target = df.loc[r["start"]:r["end"], "value"].max()

    spans = [(s, e) for s, e in zip(runs["start"], runs["end"]) if e >= t0 and s <= t1]

    # Highest unflagged event in the chosen window (rank=0 is the highest)
    matches = find_highest_unflagged_events(
        df, n=rank + 1, exclude=exclude, start=event_start, end=event_end,
        min_value=target if above_target else None)
    if len(matches) <= rank:
        print("No unflagged event found")
        return matches
    matches["rel_diff"] = (matches["value"] - target) / target
    m = matches.iloc[rank]

    # Same window width, centred on the matched peak
    half = (t1 - t0) / 2
    m0, m1 = m["time"] - half, m["time"] + half
    mwin = df.loc[m0:m1]

    fig, axes = plt.subplots(2, 1, figsize=(10, 5.6), sharey=True)

    draw_panel(axes[0], window, spans, df['flagged_mask'],
               span_colour="red", label_colour="red")
    axes[0].set_title(f"Flagged run {k}: {t0:%Y-%m-%d} to {t1:%Y-%m-%d}")

    draw_panel(axes[1], mwin, [], df['flagged_mask'],
               span_colour="0.5", label_colour="0.35")
    axes[1].plot(m["time"], m["value"], "o", ms=5, mfc="none", mec="tab:blue",
                 label=f"unflagged peak ({m['value']:.3g}, {m['rel_diff']:+.1%} vs target)")
    axes[1].legend(loc="lower right")
    axes[1].set_title(f"Highest unflagged event: {m0:%Y-%m-%d} to {m1:%Y-%m-%d}")

    for ax in axes:
        ax.axhline(target, ls="--", lw=0.8, color="orange")
    axes[0].legend(loc="lower right")

    fig.tight_layout()
    plt.show()
    return matches


def find_similar_unflagged_events(df, target, n=1, exclude=pd.Timedelta("5D"),
                                  min_sep=pd.Timedelta("2D")):
    """
    Find the n peaks whose value is closest to `target` and which have no flagged
    samples within +/- `exclude` of the peak.
    """
    flagged_mask = df['flagged_mask']
    s = df["value"]
    dt = s.index.to_series().diff().median()
    peaks, _ = find_peaks(s.fillna(-np.inf).to_numpy(),
                          distance=max(1, int(min_sep / dt)))

    cand = pd.DataFrame({"time": s.index[peaks], "value": s.iloc[peaks].to_numpy()})
    cand["rel_diff"] = (cand["value"] - target).abs() / abs(target)
    cand = cand.sort_values("rel_diff")

    keep = []
    for row in cand.itertuples():
        # Skip any peak with flagged samples nearby
        if not flagged_mask.loc[row.time - exclude : row.time + exclude].any():
            keep.append(row.Index)
            if len(keep) == n:
                break
    return cand.loc[keep].reset_index(drop=True)


def plot_run_vs_similar_event(df, runs, k, rank=0, pad=pd.Timedelta("5D"),
                              exclude=pd.Timedelta("5D")):
    r = runs.loc[k]

    # Flagged run window
    t0, t1 = r["start"] - pad, r["end"] + pad
    window = df.loc[t0:t1]
    target = df.loc[r["start"]:r["end"], "value"].max()

    # Any runs falling inside this window get shaded too
    spans = [(s, e) for s, e in zip(runs["start"], runs["end"]) if e >= t0 and s <= t1]

    # Best unflagged match (rank=0 is the closest, 1 the next closest, etc.)
    matches = find_similar_unflagged_events(df, target,  n=rank + 1, exclude=exclude)
    if len(matches) <= rank:
        print("No unflagged event found")
        return
    m = matches.iloc[rank]

    # Same window width, centred on the matched peak
    half = (t1 - t0) / 2
    m0, m1 = m["time"] - half, m["time"] + half
    mwin = df.loc[m0:m1]

    fig, axes = plt.subplots(2, 1, figsize=(10, 5.6), sharey=True)

    draw_panel(axes[0], window, spans, df['flagged_mask'],
               span_colour="red", label_colour="red")
    axes[0].set_title(f"Flagged run {k}: {t0:%Y-%m-%d} to {t1:%Y-%m-%d}")

    draw_panel(axes[1], mwin, [], df['flagged_mask'],
               span_colour="0.5", label_colour="0.35")
    axes[1].plot(m["time"], m["value"], "o", ms=5, mfc="none", mec="tab:blue",
                 label=f"unflagged peak ({m['value']:.3g}, "
                       f"{m['rel_diff']:.1%} from target)")
    axes[1].legend(loc="lower right")
    axes[1].set_title(f"Similar unflagged event: {m0:%Y-%m-%d} to {m1:%Y-%m-%d}")

    # Reference line at the truncated value in both panels
    for ax in axes:
        ax.axhline(target, ls="--", lw=0.8, color="orange",
                   label=f"truncated value ({target:.3g})")
    axes[0].legend(loc="lower right")

    fig.tight_layout()
    plt.show()
    return matches

def set_date_axis(ax, target_ticks=8):
    """Choose tick locator and label format from the span currently shown on the x-axis."""
    lo, hi = (mdates.num2date(x) for x in ax.get_xlim())
    span = hi - lo
    days = span.total_seconds() / 86400

    if days <= 2:
        # Hour scale: one or two days
        hours = days * 24
        locator = mdates.HourLocator(interval=max(1, math.ceil(hours / target_ticks)))
        fmt = "%H:%M\n%d/%m/%Y"
    elif days <= 90:
        # Day scale: up to ~3 months
        locator = mdates.DayLocator(interval=max(1, math.ceil(days / target_ticks)))
        fmt = "%d/%m/%Y"
    elif days <= 3 * 365:
        # Month scale: up to ~3 years
        months = days / 30.4
        locator = mdates.MonthLocator(interval=max(1, math.ceil(months / target_ticks)))
        fmt = "%b %Y"
    else:
        # Year scale: anything longer
        years = days / 365.25
        locator = mdates.YearLocator(base=max(1, math.ceil(years / target_ticks)))
        fmt = "%Y"

    ax.xaxis.set_major_locator(locator)
    ax.xaxis.set_major_formatter(mdates.DateFormatter(fmt))
    
    
def plot_qc_flag_distribution(df: pd.DataFrame, station_id: str,
                              qc_columns: list = ['X', 'Y', 'Z'],
                              qc_flags: list = ["1", "2", "3", "4", "5", "6", "7", "8", "9"],
                              zoom_to_flags: bool = False):
    """
    Plot the distribution of flagged timestamps across the full record,
    with a separate row for each QC column.

    zoom_to_flags : if True, zoom the x-axis to the span of flagged timestamps
                    (only when there are any). Default False = always show the
                    full time period available in df.
    """
    flag_padded = normalize_flag_to_3char(df["flag"])
    colours = {'X': "steelblue", 'Y': "firebrick", 'Z': "seagreen"}

    digits = pd.DataFrame({"X": flag_padded.str[0],
                           "Y": flag_padded.str[1],
                           "Z": flag_padded.str[2]})

    fig, axes = plt.subplots(len(qc_columns), 1,
                             figsize=(14, len(qc_columns) * 1.5),
                             sharex=True, squeeze=False)
    axes = axes.ravel()

    flagged = {}
    for ax, col_name in zip(axes, qc_columns):
        flagged_mask = digits[col_name].isin(qc_flags)
        flagged_timestamps = df.index[flagged_mask]
        flagged[col_name] = flagged_timestamps

        ax.axhspan(0, 1, color="lightgrey", alpha=0.3)
        ax.vlines(flagged_timestamps, ymin=0, ymax=1,
                  color=colours[col_name], linewidth=0.5, alpha=0.7)

        ax.set_yticks([])
        ax.set_ylabel(f"{col_name}", rotation=0, labelpad=40, va="center")
        ax.set_title(f"{flagged_mask.sum()} flagged timesteps", fontsize=9, loc="right")

    # X-limits: full record by default
    lo, hi = df.index.min(), df.index.max()
    if zoom_to_flags:
        all_ts = pd.DatetimeIndex(np.concatenate([v.values for v in flagged.values()]))
        if len(all_ts):
            lo, hi = all_ts.min(), all_ts.max()
            if lo == hi:                       # single timestamp: give it some width
                lo, hi = lo - pd.Timedelta("12h"), hi + pd.Timedelta("12h")
    axes[-1].set_xlim(lo, hi)                  # sharex=True, so this applies to all rows

    set_date_axis(axes[-1])

    fig.suptitle(f"Station {station_id} — Distribution of flagged timestamps by QC column", y=1.02)
    plt.tight_layout()

    return fig, flagged

def find_runs (df, station_id, qc_col_idx, qc_flag):
    
    flag_padded = normalize_flag_to_3char(df["flag"])
    col_names = {0: "X", 1: "Y", 2: "Z"}
    col_name = col_names[qc_col_idx]

    # Extract all digit positions in one pass
    digits = pd.DataFrame({"X": flag_padded.str[0],"Y": flag_padded.str[1],"Z": flag_padded.str[2],})

    # Find timestamps where this column has a flagged value
    flagged_mask = digits[col_name] == qc_flag
    flagged_timestamps = df.index[flagged_mask]
    
    # New run starts wherever the mask value changes
    run_id = (flagged_mask != flagged_mask.shift()).cumsum()

    # Keep only flagged rows, then split by run
    flagged_runs = [group for _, group in df[flagged_mask].groupby(run_id[flagged_mask])]

    # Get just this bit of the dataframe
    # df = df.loc[flagged_timestamps]
    
    df['flagged_mask'] = flagged_mask
    
    return flagged_runs, df

def plot_run(runs, df, cluster_id, pad = pd.Timedelta("1D")):
    
    run_data = runs[runs["cluster"] == cluster_id]
    
    t0 = run_data["start"].min() - pad
    t1 = run_data["end"].max() + pad
    window = df.loc[t0:t1]
    #flagged_in_window = window[flagged_mask.loc[window.index]]
    flagged_in_window = window[df['flagged_mask'].loc[window.index]]

    fig, ax = plt.subplots(figsize=(10, 3))
    ax.plot(window.index, window["value"], "-o", ms=1, lw=0.8, color="0.3")
    ax.plot(flagged_in_window.index, flagged_in_window["value"], "o", ms=2,
            color="red",
            label=f"flagged samples (n={len(flagged_in_window)}, {len(run_data)} runs)")

    for r in run_data.itertuples():
        ax.axvspan(r.start, r.end, color="red", alpha=0.25, lw=0)

        vals = window.loc[r.start:r.end, "value"]
        lo, hi = vals.min(), vals.max()
        text = f"{hi:.3g}" if np.isclose(lo, hi) else f"{lo:.3g}–{hi:.3g}"

        ax.annotate(text,
                    xy=(r.start + (r.end - r.start) / 2, hi),
                    xytext=(0, 6), textcoords="offset points",
                    ha="center", va="bottom", fontsize=7, color="red")

    ax.margins(y=0.15)  # headroom so labels aren't clipped
    ax.set_title(f"Flagged periods: {t0:%Y-%m-%d} to {t1:%Y-%m-%d}")
    ax.set_ylabel("value")
    ax.legend(loc="lower right")
    plt.show()
    return fig

def plot_cluster_vs_years(runs, df, cluster_id, years, pad=pd.Timedelta("1D")):
    if np.isscalar(years):
        years = [years]

    grp = runs[runs["cluster"] == cluster_id]
    t0 = grp["start"].min() - pad
    t1 = grp["end"].max() + pad
    spans = list(zip(grp["start"], grp["end"]))

    fig, axes = plt.subplots(1 + len(years), 1, figsize=(10, 2.8 * (1 + len(years))),
                             sharey=True, squeeze=False)
    axes = axes[:, 0]

    # Top: the flagged cluster
    window = df.loc[t0:t1]
    draw_panel(axes[0], window, spans, df['flagged_mask'],
               span_colour="red", label_colour="red")
    axes[0].set_title(f"Cluster {cluster_id} ({len(grp)} runs): {t0:%Y-%m-%d} to {t1:%Y-%m-%d}")

    # Below: the same calendar period in each comparison year
    for ax, year in zip(axes[1:], years):
        shift = pd.DateOffset(years=year - grp["start"].min().year)
        c0, c1 = t0 + shift, t1 + shift
        cwin = df.loc[c0:c1]

        if cwin.empty:
            ax.text(0.5, 0.5, f"No data for {year}", transform=ax.transAxes,
                    ha="center", va="center", color="0.5")
        else:
            cspans = [(s + shift, e + shift) for s, e in spans]
            draw_panel(ax, cwin, cspans, df['flagged_mask'],
                       span_colour="0.5", label_colour="0.35")
        ax.set_title(f"Equivalent period in {year}: {c0:%Y-%m-%d} to {c1:%Y-%m-%d}")

    fig.tight_layout()
    plt.show()
    
def draw_panel(ax, window, spans, mask, span_colour, label_colour, label_prefix=""):
    """Plot a window, shade each (start, end) span, mark flagged samples, label span values."""
    fl = window[mask.loc[window.index]]

    ax.plot(window.index, window["value"], "-o", ms=1, lw=0.8, color="0.3")
    if len(fl):
        ax.plot(fl.index, fl["value"], "o", ms=2, color="red",
                label=f"flagged samples (n={len(fl)})")

    for start, end in spans:
        ax.axvspan(start, end, color=span_colour, alpha=0.25, lw=0)

        vals = window.loc[start:end, "value"]
        if vals.empty:
            continue
        lo, hi = vals.min(), vals.max()
        text = f"{hi:.3g}" if np.isclose(lo, hi) else f"{lo:.3g}–{hi:.3g}"
        ax.annotate(label_prefix + text,
                    xy=(start + (end - start) / 2, hi),
                    xytext=(0, 6), textcoords="offset points",
                    ha="center", va="bottom", fontsize=7, color=label_colour)

    ax.margins(y=0.15)
    ax.set_ylabel("value")
    if len(fl):
        ax.legend(loc="lower right")


def load_station_data(station_id: str) -> pd.DataFrame:
    url = f"https://catalogue.ceh.ac.uk/datastore/eidchub/211710ac-f01b-4b52-807f-373babb1c368/1_RiverFlowStations/{station_id}.csv"
    return pd.read_csv(url, parse_dates=["datetime"], index_col="datetime")

def explore_qc_flags(
    df: pd.DataFrame,
    station_id: str,
    print_summary_table : bool = False,
    qc_columns: list = [0, 1, 2],
    qc_flags: list = ["1", "2", "3", "4", "5", "6", "7", "8", "9"],):
    """
    Explore how many timesteps would be flagged for each combination of
    qc_column and qc_flag value, to inform selection before running interpolation.
    Flag value 0 is excluded as it indicates no quality issue.

    Parameters
    ----------
    df : pd.DataFrame
        The dataframe with datetime index and 'flag' column.
    station_id : str
        Station ID, used in plot title.
    qc_columns : list
        Which QC digit positions to explore (0=X, 1=Y, 2=Z). Default is all three.
    qc_flags : list
        Which digit values to explore. Default is 1-9 (0 excluded as it means no issue).
    """

    # start = time.time()

    flag_padded = normalize_flag_to_3char(df["flag"])
    col_names = {0: "X", 1: "Y", 2: "Z"}
    total = len(df)

    # Extract all digit positions in one pass
    digits = pd.DataFrame({"X": flag_padded.str[0],"Y": flag_padded.str[1],"Z": flag_padded.str[2],})

    rows = []
    for col_idx, col_name in col_names.items():
        if col_idx not in qc_columns:
            continue
        counts = digits[col_name].value_counts()
        for flag in qc_flags:
            n_flagged = counts.get(flag, 0)
            rows.append({"qc_column": f"{col_idx} ({col_name})","qc_flag": flag,"n_flagged": n_flagged,
                         "pct_flagged": round(100 * n_flagged / total, 2),})

    summary = pd.DataFrame(rows)
    non_zero = summary[summary["n_flagged"] > 0]

    # elapsed = time.time() - start
    # print(f"Summary built in {elapsed:.3f}s")

    # Print summary table
    if print_summary_table ==True:
        print(f"\nStation {station_id} — Flagged timesteps by QC column and flag value")
        print(f"Total timesteps: {total}\n")
        if non_zero.empty:
            print("No flagged timesteps found for any combination.")
            return summary
        else:
            print(non_zero.to_string(index=False))

    # Only plot flag values that actually appear in the data
    active_flags = non_zero["qc_flag"].unique()
    pivot = summary[summary["qc_flag"].isin(active_flags)].pivot(
        index="qc_flag", columns="qc_column", values="n_flagged")

    fig, ax = plt.subplots(figsize=(6, 3))

    im = ax.imshow(pivot.values, aspect="auto", cmap="Reds")
    ax.set_xticks(range(len(pivot.columns)))
    ax.set_xticklabels(pivot.columns)
    ax.set_yticks(range(len(pivot.index)))
    ax.set_yticklabels(pivot.index)
    ax.set_title(f"Station {station_id} — Flagged timesteps by QC column and flag value")
    ax.set_xlabel("QC column")
    ax.set_ylabel("Flag value")
    plt.colorbar(im, ax=ax)

    for r in range(pivot.shape[0]):
        for c in range(pivot.shape[1]):
            val = pivot.values[r, c]
            if val > 0:
                ax.text(c, r, str(int(val)), ha="center", va="center",
                        color="black" if val < pivot.values.max() * 0.7 else "white",
                        fontsize=8)

    plt.tight_layout()
    plt.show()

    return summary

# def plot_qc_flag_distribution(df: pd.DataFrame, station_id: str, qc_columns: list = [0, 1, 2],
#     qc_flags: list = ["1", "2", "3", "4", "5", "6", "7", "8", "9"]):
    
#     """
#     Plot the distribution of flagged timestamps across the full record,
#     with a separate row for each QC column so it is easy to see whether
#     the three checks flag the same periods or different ones.
#     Parameters
#     ----------
#     df : pd.DataFrame
#         The dataframe with datetime index and 'flag' column.
#     station_id : str
#         Station ID, used in plot title.
#     qc_columns : list
#         Which QC digit positions to plot (0=X, 1=Y, 2=Z). Default is all three.
#     qc_flags : list
#         Which digit values to treat as flagged. Default is 1-9.
#     """

#     flag_padded = normalize_flag_to_3char(df["flag"])
#     col_names = {0: "X", 1: "Y", 2: "Z"}
#     colours = {0: "steelblue", 1: "firebrick", 2: "seagreen"}

#     # Extract all digit positions in one pass
#     digits = pd.DataFrame({"X": flag_padded.str[0],"Y": flag_padded.str[1],"Z": flag_padded.str[2],})

#     fig, axes = plt.subplots(len(qc_columns), 1,figsize=(14, len(qc_columns) * 1.5), sharex=True)

#     # Handle case where only one column is requested
#     if len(qc_columns) == 1:
#         axes = [axes]

#     for ax, col_idx in zip(axes, qc_columns):
#         col_name = col_names[col_idx]

#         # Find timestamps where this column has a flagged value
#         flagged_mask = digits[col_name].isin(qc_flags)
#         flagged_timestamps = df.index[flagged_mask]

#         ax.axhspan(0, 1, color="lightgrey", alpha=0.3)
#         ax.vlines(flagged_timestamps,ymin=0, ymax=1,color=colours[col_idx],linewidth=0.5, alpha=0.7)

#         ax.set_yticks([])
#         ax.set_ylabel(f"{col_idx} ({col_name})", rotation=0, labelpad=40, va="center")
#         ax.set_title(f"{flagged_mask.sum()} flagged timesteps", fontsize=9, loc="right")

#     axes[-1].set_xlabel("Datetime")
#     fig.suptitle(f"Station {station_id} — Distribution of flagged timestamps by QC column", y=1.02)
#     plt.tight_layout()
#     return fig, flagged_timestamps

def plot_flagged_clusters(
    df: pd.DataFrame,
    clusters: list,
    station_id: str,
    interp_log: pd.DataFrame = None,
    show_interpolated: bool = False,
    n_context: int = 10,):
    """
    Plot a zoomed window around each contiguous cluster of flagged values.

    Parameters
    ----------
    df : pd.DataFrame
        The dataframe with datetime index and 'value' column.
    clusters : list
        List of arrays of integer positions, one per contiguous cluster.
    station_id : str
        Station ID, used in plot titles.
    interp_log : pd.DataFrame, optional
        Interpolation log with columns ['station', 'datetime', 'old_value', 'new_value'].
        Required if show_interpolated=True.
    show_interpolated : bool
        If True, overlay interpolated values in green. Requires interp_log. Default False.
    n_context : int
        Number of real (non-NaN) values to show either side of each cluster. Default 10.
    """

    if show_interpolated and interp_log is None:
        raise ValueError("interp_log must be provided when show_interpolated=True.")

    print(f"{len(clusters)} cluster(s) of flagged points found.")

    log_indexed = interp_log.set_index("datetime") if interp_log is not None else None

    for i, cluster in enumerate(clusters):

        window_start, window_end = get_window_with_real_values(df, cluster, n=n_context)
        df_window = df.iloc[window_start:window_end + 1].copy()
        cluster_datetimes = df.index[cluster]

        # Get old values — from df directly if no log provided, otherwise from log
        if log_indexed is not None:
            old_values_cluster = log_indexed.loc[cluster_datetimes, "old_value"]
        else:
            old_values_cluster = df.loc[cluster_datetimes, "value"]

        # Restore original values as the base line
        df_window.loc[cluster_datetimes, "value"] = old_values_cluster.values

        # Scale scatter point size based on number of points in the window
        n_points = len(df_window)
        point_size = max(10, min(80, 800 / n_points))

        fig, ax = plt.subplots(figsize=(10, 4))

        ax.plot(df_window.index, df_window["value"],
                color="black", linewidth=0.8)
        ax.scatter(df_window.index, df_window["value"],
                   color="black", s=point_size, label="Time series")

        # Always show flagged values in red
        ax.scatter(cluster_datetimes, old_values_cluster,
                   color="red", zorder=5, s=point_size * 1.5,
                   label=f"Flagged values ({len(cluster)} points)")

        if show_interpolated:
            new_values = log_indexed.loc[cluster_datetimes, "new_value"]
            ax.scatter(cluster_datetimes, new_values,
                       color="green", zorder=6, s=point_size * 1.5, marker="x",
                       label=f"Interpolated values ({len(cluster)} points)")

            still_nan = new_values[new_values.isna()]
            if not still_nan.empty:
                ax.scatter(still_nan.index, old_values_cluster.loc[still_nan.index],
                           color="orange", zorder=6, s=point_size * 1.5, marker="x",
                           label=f"Could not interpolate ({len(still_nan)} points)")

        # Format x axis based on time range of the window
        time_range = df_window.index[-1] - df_window.index[0]
        if time_range <= pd.Timedelta(days=2):
            ax.xaxis.set_major_formatter(mdates.DateFormatter("%d %b\n%H:%M"))
        elif time_range <= pd.Timedelta(days=30):
            ax.xaxis.set_major_formatter(mdates.DateFormatter("%d %b\n%Y"))
        else:
            ax.xaxis.set_major_formatter(mdates.DateFormatter("%b %Y"))

        plt.setp(ax.xaxis.get_majorticklabels(), rotation=0, ha="center")

        ax.set_title(f"Station {station_id} — Cluster {i + 1} of {len(clusters)} "
                     f"({'interpolated' if show_interpolated else 'original'})")
        ax.set_xlabel("Datetime")
        ax.set_ylabel("Flow value")
        ax.legend()
        fig.tight_layout()
        plt.show()

def plot_flagged_distribution(
    df: pd.DataFrame,
    flagged_rows: pd.Series,
    station_id: str,):
    """
    Plot the distribution of flagged timestamps across the full record.

    Parameters
    ----------
    df : pd.DataFrame
        The dataframe with datetime index.
    flagged_rows : pd.Series
        Boolean mask indicating which rows are flagged.
    station_id : str
        Station ID, used in plot title.
    """

    fig, ax = plt.subplots(figsize=(14, 2))

    ax.axhspan(0, 1, color="lightgrey", alpha=0.3)
    ax.vlines(df.loc[flagged_rows].index,ymin=0, ymax=1,color="red", linewidth=0.5, alpha=0.7)

    ax.set_title(f"Station {station_id} — Distribution of flagged timestamps across the full record "
                 f"({flagged_rows.sum()} flagged out of {len(df)} total)")
    ax.set_xlabel("Datetime")
    ax.set_yticks([])
    plt.tight_layout()
    plt.show()        

def find_truncated_flows(
    df,
    time_col="datetime",
    value_col="value",
    min_run=4,            # min consecutive identical values to count as "truncated"
    tol=0.0,              # absolute tolerance for "identical" (e.g. 0.001 for rounded data)
    high_quantile=0.95,   # runs at/above this quantile are labelled as high-flow (likely ceiling)
    ignore_zero=True,     # zero-flow runs are usually genuine dry spells, so skip them
    only_high=False,      # True -> only keep runs at high flows (peak clipping)
    plot=True
):
    df_local = df.reset_index().copy()
    d = (df_local[[time_col, value_col]].dropna().sort_values(time_col).reset_index(drop=True))
    t = d[time_col]
    v = d[value_col].to_numpy(float)

    # A run continues if value is unchanged AND there's no time gap
    step = t.diff().median()
    contiguous = (t.diff().iloc[1:] <= 1.5 * step).to_numpy()
#     same = np.abs(np.diff(v)) <= tol
#     new_run = np.ones(len(d), bool)
#     new_run[1:] = ~(same & contiguous)
#     d["run"] = np.cumsum(new_run)
#     d["i"] = np.arange(len(d))
    
    
    run_id = np.zeros(len(v), int)
    anchor, r = v[0], 0
    for i in range(1, len(v)):
        if not (abs(v[i] - anchor) <= tol and contiguous[i-1]):
            r += 1
            anchor = v[i]
        run_id[i] = r
    d["run"] = run_id  
    d["i"] = np.arange(len(d))

    runs = (d.groupby("run")
              .agg(start=(time_col, "first"), end=(time_col, "last"),
                   i0=("i", "first"), i1=("i", "last"),
                   n=(value_col, "size"), value=(value_col, "first"))
              .reset_index(drop=True))

    high_thr = np.quantile(v, high_quantile)
    runs = runs[runs["n"] >= min_run].copy()
    if ignore_zero:
        runs = runs[runs["value"] > 0]
    runs["at_high_flow"] = runs["value"] >= high_thr
    runs["is_global_max"] = np.isclose(runs["value"], v.max(), atol=max(tol, 1e-12))
    if only_high:
        runs = runs[runs["at_high_flow"]]
    runs["duration"] = runs["end"] - runs["start"]
    runs = runs.sort_values(["value", "n"], ascending=False).reset_index(drop=True)

    # Repeated hits on the same high value across separate runs = strong ceiling evidence
    hi = runs[runs["at_high_flow"]]
    if len(hi):
        counts = hi["value"].round(6).value_counts()
        repeated = counts[counts > 1]
        #if len(repeated):
            #print("Same high value hit in multiple separate runs (likely a ceiling):")
            # print(repeated.to_string(), "\n")

    plot_truncated_flows(runs, d, t, v, plot=plot, max_panels= 10, high_quantile = high_quantile)            
            
    return runs, repeated

def plot_truncated_flows(runs, d, t, v, plot=True,
                        max_panels=6,         # number of zoomed panels
                        pad=24,               # samples of context either side in zoomed panels
                         high_quantile=0.95
                         ):
    
    high_thr = np.quantile(v, high_quantile)
    
    
    n_pan = min(max_panels, len(runs))
                         
    ncols = 2
    nrows = 1 + int(np.ceil(n_pan / ncols))
    fig = plt.figure(figsize=(14, 3 + 2.6 * (nrows - 1)))
    gs = fig.add_gridspec(nrows, ncols)

    # Overview
    ax = fig.add_subplot(gs[0, :])
    ax.plot(t, v, lw=0.6, color="0.3")
    mask = np.zeros(len(d), bool)
    for _, r in runs.iterrows():
        mask[r.i0:r.i1 + 1] = True
        ax.axvspan(r.start, r.end, color="red", alpha=0.25, lw=0)
    ax.scatter(t[mask], v[mask], s=6, color="red", zorder=3,
               label=f"truncated samples ({len(runs)} runs)")
    ax.axhline(high_thr, ls="--", color="orange", lw=0.8,
               label=f"{high_quantile:.0%} quantile")
    ax.set_title("Flow record with suspected truncated periods")
    ax.set_ylabel("value")
    ax.legend(loc="upper right")

    # Zoomed panels
    for k, (_, r) in enumerate(runs.head(n_pan).iterrows()):
        ax = fig.add_subplot(gs[1 + k // ncols, k % ncols])
        a, b = max(r.i0 - pad, 0), min(r.i1 + pad, len(d) - 1)
        ax.plot(t[a:b + 1], v[a:b + 1], "-o", ms=3, lw=0.8, color="0.3")
        ax.plot(t[r.i0:r.i1 + 1], v[r.i0:r.i1 + 1], "o", ms=5, color="red")
        ax.axhline(r.value, ls=":", color="red", lw=0.8)
        ax.set_title(f"{r.start:%Y-%m-%d %H:%M} | {r.n} steps | value={r.value:g}",
                     fontsize=9)
        ax.tick_params(axis="x", rotation=30, labelsize=8)

    fig.tight_layout()
    plt.show()    
        
def get_window_with_real_values(df, cluster, n=10):
    # Work backwards from the cluster start until we have n real values
    pre_cluster = df.iloc[:cluster[0]]["value"].dropna()
    if len(pre_cluster) >= n:
        window_start = df.index.get_loc(pre_cluster.iloc[-n:].index[0])
    else:
        window_start = df.index.get_loc(pre_cluster.index[0]) if len(pre_cluster) > 0 else cluster[0]
    
    # Work forwards from the cluster end until we have n real values
    post_cluster = df.iloc[cluster[-1]+1:]["value"].dropna()
    if len(post_cluster) >= n:
        window_end = df.index.get_loc(post_cluster.iloc[:n].index[-1])
    else:
        window_end = df.index.get_loc(post_cluster.index[-1]) if len(post_cluster) > 0 else cluster[-1]
    
    return window_start, window_end        

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

def run_interpolation(df, flagged_rows, station_id, round_decimals=2):
    # =============================================================================
    # STEP 1: PREPARE THE DATA FOR INTERPOLATION
    # =============================================================================
    # Time-based interpolation requires the data to be sorted chronologically
    # and for each timestamp to appear only once. If duplicate timestamps exist,
    # we collapse them by taking the mean, since interpolation cannot handle
    # multiple values at the same point in time.

    df = df.sort_index()
    if not df.index.is_unique:
        df = df.groupby(level=0).mean(numeric_only=True)
        
    # Recompute the mask against the now-sorted index
    flagged_rows = flagged_rows.reindex(df.index, fill_value=False)        
        
    # =============================================================================
    # STEP 2: RECORD THE ORIGINAL VALUES BEFORE INTERPOLATION
    # =============================================================================
    # Before we overwrite any values, we save the original values of the flagged
    # rows. This gives us a log of what changed, which is useful for auditing
    # and quality checking the interpolation afterwards.    

    old_values = (
        df.loc[flagged_rows, ["value"]]
        .rename(columns={"value": "old_value"})
        .reset_index()
    )

    # =============================================================================
    # STEP 3: REPLACE FLAGGED VALUES WITH INTERPOLATED ESTIMATES
    # =============================================================================
    # We set the flagged values to NaN (null), then use time-based linear
    # interpolation to estimate replacement values. Unlike simple positional
    # interpolation, time-based interpolation accounts for uneven gaps between
    # timestamps — so a 6-hour gap is treated differently to a 1-hour gap.
    
    df.loc[flagged_rows, "value"] = pd.NA
    df["value"] = df["value"].interpolate(method="time")

    if (round_decimals is not None) and (round_decimals >= 0):
        df["value"] = df["value"].round(round_decimals)

    # =============================================================================
    # STEP 4: BUILD THE INTERPOLATION LOG
    # =============================================================================
    # Finally, we combine the original values (saved in Step 3) with the new
    # interpolated values to produce a log of every change made. This log can
    # be saved to a CSV for auditing purposes.

    old_values["new_value"] = old_values["datetime"].map(df["value"])
    old_values["station"] = station_id
    interp_log = old_values[["station", "datetime", "old_value", "new_value"]]
    print("\nInterpolation log (old vs new values):")
    print(interp_log.head(10))

    # =============================================================================
    # CHECK: IDENTIFY POINTS THAT COULD NOT BE INTERPOLATED
    # =============================================================================
    # Time-based interpolation cannot fill values at the edges of the record
    # where there is no preceding or following real value to interpolate from.
    # These will remain as NaN in the cleaned data.

    unresolved = interp_log[interp_log["new_value"].isna()]
    if not unresolved.empty:
        print(f"Warning: {len(unresolved)} point(s) could not be interpolated.")
    else:
        print("All flagged points were successfully interpolated.")

    return interp_log, unresolved, df


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



####################### VISUAL REVIEW FUNCTIONS
# # --- Functions ---
# def show_event(idx, current_out, station_id, df, runs_list, btn_back ):
#     current_out.clear_output()

#     start, end = runs_list[idx]
#     window = df.loc[start - pd.Timedelta(days=1): end + pd.Timedelta(days=1), "value"]

#     with current_out:
#         fig, ax = plt.subplots(figsize=(10, 4))
#         ax.plot(window.index, window.values, lw=1)
#         ax.axvspan(start, end, color="red", alpha=0.3)
#         ax.set_title(
#             f"{station_id} ({idx+1}/{len(runs_list)}) — "
#             f"{start:%Y-%m-%d %H:%M} to {end:%Y-%m-%d %H:%M}")
#         plt.tight_layout()
#         plt.show()

#     btn_back.disabled = (idx == 0)


# def update_progress():
#     progress.value = len(all_results)


# def log_result(text):
#     with history_out:
#         print(text)


# def next_event():
#     global i
#     i += 1
#     if i < len(runs_list):
#         show_event(i)
#     else:
#         current_out.clear_output()
#         with history_out:
#             print("🎉 Done!")


# def prev_event():
#     global i

#     if i > 0:
#         i -= 1

#         if len(all_results) > i:
#             all_results.pop()

#         update_progress()
#         show_event(i)

#         with history_out:
#             print(f"↩️ Went back to event {i+1}")


# def on_true(b):
#     start, end = runs_list[i]

#     if len(all_results) > i:
#         all_results[i] = {"station": station_id, "start": start, "end": end, "real": True}
#     else:
#         all_results.append({"station": station_id, "start": start, "end": end, "real": True})

#     log_result(f"✅ {i+1}: {start} – {end} → True")
#     update_progress()
#     next_event()


def on_false(b):
    start, end = runs_list[i]

    if len(all_results) > i:
        all_results[i] = {"station": station_id, "start": start, "end": end, "real": False}
    else:
        all_results.append({"station": station_id, "start": start, "end": end, "real": False})

    log_result(f"❌ {i+1}: {start} – {end} → False")
    update_progress()
    next_event()
    