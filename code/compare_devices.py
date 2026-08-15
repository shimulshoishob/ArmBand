#!/usr/bin/env python3
"""Compare the EMG armband vs. a normal mouse on ISO 9241-9 / Fitts' law metrics.

Reads the CSV logs written by code/mouse.py (fitts_log.csv plus the matching
*_block_summary.csv and *_regression.csv), normalizes the differing schemas
(the older compare_mouse log has fewer columns), and renders comparison
figures so the difference between a normal mouse, the previous EMG device
(old_emg) and the improved EMG device (new_emg) is easy to see.

The figures are written as high-resolution PNGs (and PDFs) into the output
folder, ready to be embedded in the thesis.  A per-device aggregate table is
also saved as comparison_summary.csv.

Usage:
    python code/compare_devices.py                     # scan default folders
    python code/compare_devices.py path/to/folder      # scan one folder
    python code/compare_devices.py a.csv b.csv         # explicit log files
    python code/compare_devices.py --out report/ --dir code/ --dir compare_mouse/
"""

import argparse
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import matplotlib

matplotlib.use("Agg")  # headless-safe: renders straight to files
import matplotlib.pyplot as plt

# --------------------------------------------------------------------------
# Constants
# --------------------------------------------------------------------------

# System labels in the app's "Test System" selector are stored as
# normal_mouse / old_emg / new_emg. Anything else gets a cycle color.
SYSTEM_PALETTE = {
    "normal_mouse": "#4C72B0",
    "old_emg": "#C44E52",
    "new_emg": "#55A868",
}

NUMERIC_COLUMNS = [
    "MT", "D", "W", "ID", "De", "We", "IDe", "TP", "path_efficiency",
    "re_entry_count", "reversal_count_x", "reversal_count_y",
    "time_to_first_move",
]
BOOL_COLUMNS = ["click_correct", "click_error", "wrong_click", "spurious_click"]


# --------------------------------------------------------------------------
# Data loading / normalization
# --------------------------------------------------------------------------

def coerce_numeric(df, column):
    if column in df.columns:
        df[column] = pd.to_numeric(df[column], errors="coerce")


def coerce_bool(df, column):
    if column in df.columns:
        df[column] = (
            df[column].astype(str).str.strip().str.lower()
            .map({"true": True, "false": False, "1": True, "0": False})
            .fillna(False).astype(bool)
        )
    else:
        df[column] = False


def normalize_trials(df):
    """Return a copy of a trials CSV with a canonical column layout."""
    df = df.copy()
    if "participant_id" not in df.columns:
        df["participant_id"] = "participant_01"
    df["participant_id"] = df["participant_id"].astype(str).str.strip()
    df["system"] = df["system"].astype(str).str.strip().str.lower()

    for column in NUMERIC_COLUMNS:
        coerce_numeric(df, column)
    for column in BOOL_COLUMNS:
        coerce_bool(df, column)

    # The older compare_mouse log has no nominal ID; derive it from distance
    # and width so the Fitts regression plot can still be drawn.
    if "ID" not in df.columns or df["ID"].isna().all():
        df["ID"] = np.log2(df["D"] / df["W"] + 1.0)
    if "IDe" not in df.columns or df["IDe"].isna().all():
        df["IDe"] = df["ID"]
    if "path_efficiency" not in df.columns:
        df["path_efficiency"] = np.nan
    if "click_error" not in df.columns:
        df["click_error"] = ~df["click_correct"]

    return df


def normalize_block_summaries(df):
    df = df.copy()
    if "participant_id" not in df.columns:
        df["participant_id"] = "participant_01"
    df["system"] = df["system"].astype(str).str.strip().str.lower()
    coerce_numeric(df, "mean_TP")
    return df


def find_log_sets(roots):
    """Group the three related CSVs (trials / block summary / regression).

    Returns a list of (trials_path, summary_path, regression_path) tuples,
    where each entry may be None if that file is missing.
    """
    groups = {}
    for root in roots:
        root = Path(root)
        if not root.exists():
            continue
        files = sorted(root.glob("fitts_log*.csv")) if root.is_dir() else [root]
        for fp in files:
            name = fp.name
            key = str(fp.parent)
            if name.endswith("_block_summary.csv"):
                groups.setdefault(key, {})["summary"] = fp
            elif name.endswith("_regression.csv"):
                groups.setdefault(key, {})["regression"] = fp
            elif "fitts_log" in name:
                groups.setdefault(key, {})["trials"] = fp

    return [
        (group.get("trials"), group.get("summary"), group.get("regression"))
        for group in groups.values()
    ]


# --------------------------------------------------------------------------
# Statistics
# --------------------------------------------------------------------------

def fit_regression(group):
    """Fit MT = a + b * ID and return slope/intercept/R2 (None if too small)."""
    valid = group[["ID", "MT"]].dropna()
    if len(valid) < 2 or valid["ID"].nunique() < 2:
        return None
    slope, intercept = np.polyfit(valid["ID"], valid["MT"], 1)
    predicted = intercept + slope * valid["ID"]
    total = float(np.sum((valid["MT"] - valid["MT"].mean()) ** 2))
    r2 = 1.0 if total == 0 else float(1.0 - np.sum((valid["MT"] - predicted) ** 2) / total)
    return {
        "intercept_s": float(intercept),
        "slope_s_per_bit": float(slope),
        "r_squared": r2,
        "n": int(len(valid)),
    }


def aggregate_by_system(trials, summaries):
    """One summary row per device condition (across all participants)."""
    rows = []
    for system, group in trials.groupby("system", dropna=False):
        n = len(group)
        regression = fit_regression(group)
        row = {
            "system": system,
            "n_trials": n,
            "mean_MT_s": group["MT"].mean(),
            "mean_ID_bits": group["ID"].mean(),
            "mean_TP": group["TP"].mean(),
            "std_TP": group["TP"].std(ddof=1) if n > 1 else 0.0,
            "error_rate": group["click_error"].mean(),
            "wrong_click_rate": group["wrong_click"].mean(),
            "spurious_click_rate": group["spurious_click"].mean(),
            "mean_path_efficiency": group["path_efficiency"].mean(),
            "mean_re_entry": group["re_entry_count"].mean(),
            "mean_reversals": (group["reversal_count_x"] + group["reversal_count_y"]).mean(),
        }
        if regression:
            row.update({f"reg_{k}": v for k, v in regression.items()})
        rows.append(row)
    summary_df = pd.DataFrame(rows)

    # Overlay block-level means (from *_block_summary.csv) when available.
    if summaries is not None and not summaries.empty:
        block_means = (
            summaries[["system", "block_id", "mean_TP"]]
            .dropna()
            .rename(columns={"mean_TP": "block_mean_TP"})
        )
        summary_df = summary_df.merge(block_means, on="system", how="left")
    return summary_df


# --------------------------------------------------------------------------
# Plotting helpers
# --------------------------------------------------------------------------

def system_color(system, index=0):
    return SYSTEM_PALETTE.get(system, f"C{index % 10}")


def _style_axes(ax, title, xlabel, ylabel, legend=True):
    ax.set_title(title, fontweight="bold", pad=10)
    ax.set_xlabel(xlabel)
    ax.set_ylabel(ylabel)
    ax.grid(axis="y", linestyle=":", alpha=0.4)
    if legend:
        ax.legend(frameon=False, fontsize=9)


def plot_throughput(agg, trials, ax=None):
    """Mean throughput per device with per-trial and per-block points."""
    own = ax is None
    if own:
        fig, ax = plt.subplots(figsize=(7.5, 5.0), dpi=140)
    systems = list(agg["system"])
    colors = [system_color(s, i) for i, s in enumerate(systems)]
    means = agg["mean_TP"]
    stds = agg["std_TP"].fillna(0.0)

    bars = ax.bar(systems, means, yerr=stds, color=colors, alpha=0.85,
                  capsize=5, error_kw={"elinewidth": 1.5})
    for bar in bars:
        bar.set_edgecolor("black")
        bar.set_linewidth(0.6)

    # Individual trial throughput (jittered) so sample size is visible.
    rng = np.random.default_rng(42)
    for i, system in enumerate(systems):
        values = trials[trials["system"] == system]["TP"].dropna()
        xs = rng.normal(i, 0.07, len(values))
        ax.scatter(xs, values, s=16, color=colors[i], alpha=0.45,
                   zorder=3, edgecolors="none")

    # Block-level means as X markers, when the app exported them.
    if "block_mean_TP" in agg.columns:
        for i, system in enumerate(systems):
            block_means = agg.loc[agg["system"] == system, "block_mean_TP"].dropna()
            if len(block_means):
                ax.scatter([i] * len(block_means), block_means, marker="X",
                           s=55, color=colors[i], edgecolors="black",
                           linewidths=0.5, zorder=4)

    for i, (mean, std) in enumerate(zip(means, stds)):
        ax.text(i, mean + std + 0.05, f"{mean:.2f} \u00b1 {std:.2f}",
                ha="center", va="bottom", fontsize=9, fontweight="bold")

    _style_axes(ax, "Mean throughput by device (higher is better)",
                "Device", "Throughput (bits/s)", legend=False)
    ax.set_ylim(bottom=0)
    if own:
        fig.tight_layout()
        return fig


def plot_regression(trials, ax=None):
    """Fitts' law regression: movement time vs. index of difficulty."""
    own = ax is None
    if own:
        fig, ax = plt.subplots(figsize=(7.5, 5.0), dpi=140)
    systems = sorted(trials["system"].dropna().unique())
    colors = [system_color(s, i) for i, s in enumerate(systems)]

    for i, system in enumerate(systems):
        group = trials[trials["system"] == system].dropna(subset=["ID", "MT"])
        if group.empty:
            continue
        ax.scatter(group["ID"], group["MT"], s=24, color=colors[i], alpha=0.7,
                   label=system, edgecolors="white", linewidth=0.5)
        fit = fit_regression(group)
        if fit:
            xs = np.linspace(group["ID"].min(), group["ID"].max(), 100)
            ys = fit["intercept_s"] + fit["slope_s_per_bit"] * xs
            ax.plot(xs, ys, color=colors[i], linewidth=2, linestyle="--",
                    label=f"{system} fit  (MT = {fit['intercept_s']:.2f} + "
                          f"{fit['slope_s_per_bit']:.2f}\u00b7ID, R\u00b2={fit['r_squared']:.2f})")

    _style_axes(ax, "Fitts' law: movement time vs. index of difficulty",
                "Index of Difficulty ID (bits)", "Movement Time (s)")
    ax.set_xlim(left=0)
    ax.set_ylim(bottom=0)
    if own:
        fig.tight_layout()
        return fig


def plot_errors(agg, ax=None):
    """Click error rates per device."""
    own = ax is None
    if own:
        fig, ax = plt.subplots(figsize=(7.5, 5.0), dpi=140)
    systems = list(agg["system"])
    metrics = [
        ("error_rate", "Error rate"),
        ("wrong_click_rate", "Wrong target click"),
        ("spurious_click_rate", "Spurious click"),
    ]
    x = np.arange(len(systems))
    width = 0.26
    for j, (column, label) in enumerate(metrics):
        values = (agg[column].fillna(0.0) * 100.0).to_numpy(dtype=float)
        bars = ax.bar(x + (j - 1) * width, values, width, label=label)
        for bar, value in zip(bars, values):
            bar.set_color(plt.cm.tab10(0.4 + 0.25 * j))
            if value > 0:
                ax.text(bar.get_x() + bar.get_width() / 2, value + 0.5,
                        f"{value:.1f}%", ha="center", fontsize=8)

    ax.set_xticks(x)
    ax.set_xticklabels(systems)
    _style_axes(ax, "Click error rates by device (lower is better)",
                "Device", "Rate (%)")
    ax.set_ylim(bottom=0)
    if own:
        fig.tight_layout()
        return fig


def plot_path_metrics(agg, ax=None):
    """Path efficiency, re-entries and reversals per device."""
    own = ax is None
    if own:
        fig, axes = plt.subplots(1, 3, figsize=(13.0, 4.2), dpi=140)
    else:
        axes = [ax] if not isinstance(ax, np.ndarray) else list(ax)

    systems = list(agg["system"])
    colors = [system_color(s, i) for i, s in enumerate(systems)]
    panels = [
        ("mean_path_efficiency", "Mean path efficiency", 100.0,
         "Path efficiency (%)", True),
        ("mean_re_entry", "Mean re-entries per trial", 1.0, "Re-entries", False),
        ("mean_reversals", "Mean directional reversals", 1.0, "Reversals", False),
    ]
    for panel_ax, (column, title, scale, ylabel, is_ratio) in zip(axes, panels):
        values = (agg[column].fillna(0.0) * scale).to_numpy(dtype=float)
        bars = panel_ax.bar(systems, values, color=colors, alpha=0.85)
        for bar in bars:
            bar.set_edgecolor("black")
            bar.set_linewidth(0.6)
        for bar, value in zip(bars, values):
            panel_ax.text(bar.get_x() + bar.get_width() / 2, value + (0.02 if is_ratio else 0.02),
                          f"{value:.2f}", ha="center", fontsize=8)
        panel_ax.set_title(title, fontweight="bold", pad=8)
        panel_ax.set_ylabel(ylabel)
        panel_ax.grid(axis="y", linestyle=":", alpha=0.4)
        panel_ax.set_ylim(bottom=0)

    if own:
        fig.tight_layout()
        return fig


def plot_tp_by_id(trials, ax=None):
    """Throughput within ID bands, to show how each device copes with difficulty."""
    own = ax is None
    if own:
        fig, ax = plt.subplots(figsize=(7.5, 5.0), dpi=140)
    df = trials.dropna(subset=["ID", "TP"]).copy()
    edges = [0.0, 1.5, 2.5, 3.5, 4.5, 8.0]
    labels = ["<1.5", "1.5\u20132.5", "2.5\u20133.5", "3.5\u20134.5", ">4.5"]
    df["id_band"] = pd.cut(df["ID"], bins=edges, labels=labels, right=False)
    systems = sorted(df["system"].unique())
    colors = [system_color(s, i) for i, s in enumerate(systems)]

    for i, system in enumerate(systems):
        grouped = df[df["system"] == system].groupby("id_band", observed=True)["TP"].mean()
        xs = np.arange(len(labels))
        counts = grouped.reindex(labels)
        ax.plot(xs, counts, marker="o", linewidth=2, color=colors[i], label=system)
        for j, value in enumerate(counts):
            n = len(df[(df["system"] == system) & (df["id_band"] == labels[j])])
            if not np.isnan(value) and n > 0:
                ax.annotate(f"{value:.1f}", (j, value), textcoords="offset points",
                            xytext=(0, 6), ha="center", fontsize=8)

    ax.set_xticks(np.arange(len(labels)))
    ax.set_xticklabels(labels)
    _style_axes(ax, "Throughput by index-of-difficulty band",
                "Index of Difficulty ID (bits)", "Throughput (bits/s)")
    ax.set_ylim(bottom=0)
    if own:
        fig.tight_layout()
        return fig


def build_overview(agg, trials, out_dir):
    """One compact 2x2 figure for a single results slide."""
    fig, axes = plt.subplots(2, 2, figsize=(12.5, 9.0), dpi=150)
    plot_throughput(agg, trials, ax=axes[0][0])
    plot_errors(agg, ax=axes[0][1])
    plot_path_metrics(agg, ax=axes[1][0])
    plot_regression(trials, ax=axes[1][1])
    fig.tight_layout()
    path = out_dir / "overview_all_metrics.png"
    fig.savefig(path, bbox_inches="tight")
    pdf_path = out_dir / "overview_all_metrics.pdf"
    fig.savefig(pdf_path, bbox_inches="tight")
    plt.close(fig)
    return path, pdf_path


# --------------------------------------------------------------------------
# Main
# --------------------------------------------------------------------------

def parse_args(argv):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("paths", nargs="*", help="Folders or log files to analyse.")
    parser.add_argument("--dir", dest="dirs", action="append", default=[],
                        help="Extra folder to scan (repeatable).")
    parser.add_argument("--out", default="comparison_report",
                        help="Output folder for figures (default: comparison_report).")
    parser.add_argument("--system", default=None, nargs="*",
                        help="Only keep these systems (e.g. --system normal_mouse new_emg).")
    return parser.parse_args(argv)


def main(argv=None):
    args = parse_args(argv)

    roots = list(args.paths) + list(args.dirs)
    if not roots:
        roots = [".", "compare_mouse", "code"]

    log_sets = find_log_sets(roots)
    if not log_sets:
        sys.exit("No fitts_log*.csv files found. Record Fitts trials first, then re-run.")

    all_trials = []
    all_summaries = []
    for trials_path, summary_path, _regression_path in log_sets:
        if trials_path is not None:
            try:
                frame = normalize_trials(pd.read_csv(trials_path))
            except Exception as exc:
                print(f"Warning: could not read {trials_path}: {exc}")
                continue
            if frame.empty:
                continue
            all_trials.append(frame)
            print(f"Loaded {len(frame)} trials from {trials_path}")
        if summary_path is not None:
            try:
                summary_frame = normalize_block_summaries(pd.read_csv(summary_path))
                all_summaries.append(summary_frame)
            except Exception as exc:
                print(f"Warning: could not read {summary_path}: {exc}")

    if not all_trials:
        sys.exit("No readable trial data found.")

    trials = pd.concat(all_trials, ignore_index=True).drop_duplicates().reset_index(drop=True)
    non_empty_summaries = [s for s in all_summaries if s is not None and not s.empty]
    summaries = pd.concat(non_empty_summaries, ignore_index=True) if non_empty_summaries else None

    if args.system:
        trials = trials[trials["system"].isin([s.lower() for s in args.system])]
        if summaries is not None:
            summaries = summaries[summaries["system"].isin([s.lower() for s in args.system])]

    if trials.empty:
        sys.exit(f"No trials remain after filtering systems: {args.system}")

    dup_systems = trials.groupby("system", dropna=False)["system"].count()
    for system, count in dup_systems.items():
        print(f"  {system}: {count} trials")

    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)

    agg = aggregate_by_system(trials, summaries)

    print("\n=== Per-device summary ===")
    print(agg.to_string(index=False, float_format=lambda v: f"{v:.3f}"))
    agg.to_csv(out_dir / "comparison_summary.csv", index=False)

    figures = {}
    figures["throughput"] = plot_throughput(agg, trials)
    figures["regression"] = plot_regression(trials)
    figures["errors"] = plot_errors(agg)
    figures["path_metrics"] = plot_path_metrics(agg)
    figures["tp_by_id"] = plot_tp_by_id(trials)

    saved = []
    for name, fig in figures.items():
        if fig is None:
            continue
        png_path = out_dir / f"comparison_{name}.png"
        pdf_path = out_dir / f"comparison_{name}.pdf"
        fig.savefig(png_path, bbox_inches="tight")
        fig.savefig(pdf_path, bbox_inches="tight")
        plt.close(fig)
        saved.append(str(png_path))

    overview_png, overview_pdf = build_overview(agg, trials, out_dir)
    saved.append(str(overview_png))

    print(f"\nFigures saved to {out_dir}/")
    for path in saved:
        print(f"  {path}")

    # Brief interpretation to make the numbers easy to quote in the thesis.
    if len(agg) > 1:
        best = agg.loc[agg["mean_TP"].idxmax()]
        worst_error = agg.loc[agg["error_rate"].idxmax()]
        print("\n=== Interpretation ===")
        print(f"Highest throughput: {best['system']} "
              f"({best['mean_TP']:.2f} bits/s vs. overall mean {agg['mean_TP'].mean():.2f}).")
        print(f"Lowest error rate: {agg.loc[agg['error_rate'].idxmin(), 'system']} "
              f"({agg['error_rate'].min() * 100:.1f}%); highest is "
              f"{worst_error['system']} ({worst_error['error_rate'] * 100:.1f}%).")


if __name__ == "__main__":
    main()
