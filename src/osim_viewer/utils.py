from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd
from scipy.signal import butter, filtfilt


def smooth_mot_file(
    input_path: str | Path,
    output_path: str | Path,
    cutoff_hz: float = 6.0,
    order: int = 3,
) -> None:
    """
    Smooths a .mot file using a zero-phase Butterworth low-pass filter.

    The function reads a .mot file, applies a low-pass filter to all columns
    except 'time', and writes the smoothed data to a new file while preserving
    the original header.

    Args:
        input_path: Path to the input .mot file.
        output_path: Path to save the smoothed .mot file.
        cutoff_hz: Cutoff frequency for the low-pass filter in Hz.
        order: Order of the Butterworth filter.

    Raises:
        ValueError: If the file lacks an 'endheader' or 'time' column, or does
            not contain enough rows to compute sampling rate.
    """
    input_path, output_path = Path(input_path), Path(output_path)

    # Step 1: read and split header vs data
    with open(input_path, "r", encoding="utf-8") as f:
        lines = f.readlines()

    # Find where the numeric table starts
    end_idx = None
    for i, line in enumerate(lines):
        if line.strip().lower() == "endheader":
            end_idx = i
            break
    if end_idx is None:
        raise ValueError("Invalid .mot file: missing 'endheader' line")

    header_lines = lines[: end_idx + 1]
    data_lines = lines[end_idx + 1 :]

    # Step 2: load into DataFrame
    # First non-empty data line defines columns (tab-separated)
    col_line = data_lines[0]
    sep = "\t" if "\t" in col_line else r"\s+"
    df = pd.read_csv(
        input_path,
        comment="#",
        sep=sep,
        skiprows=end_idx + 1,
        engine="python",
    )

    # Step 3: get sampling rate
    if "time" not in df.columns:
        raise ValueError("Missing 'time' column; cannot infer sampling rate.")
    time = df["time"].values
    if len(time) < 2:
        raise ValueError("Not enough rows to estimate sampling rate.")
    dt = np.median(np.diff(time))
    fs = 1.0 / dt  # Hz

    # Step 4: design filter (normalized cutoff)
    nyquist = 0.5 * fs
    wn = min(cutoff_hz / nyquist, 0.99)
    b, a = butter(order, wn, btype="low", analog=False)

    # Step 5: filter all numeric columns except 'time'
    smoothed = df.copy()
    for col in df.columns:
        if col.lower() == "time":
            continue
        data = df[col].astype(float).values
        if np.allclose(data, data[0]):
            continue  # skip constants
        smoothed[col] = filtfilt(b, a, data)

    # Step 6: write back with same header
    with open(output_path, "w", encoding="utf-8") as f:
        for line in header_lines:
            f.write(line)
        smoothed.to_csv(f, sep="\t", index=False, float_format="%.8f")
