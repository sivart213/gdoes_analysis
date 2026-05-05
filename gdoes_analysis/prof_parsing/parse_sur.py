# -*- coding: utf-8 -*-
"""
Insert module description/summary.

Provide any or all of the following:
1. extended summary
2. routine listings/functions/classes
3. see also
4. notes
5. references
6. examples

@author: j2cle
Created on Tue Jan 13 21:06:09 2026
"""
import struct
from pathlib import Path
from datetime import datetime

import numpy as np
import pandas as pd

from gdoes_analysis.prof_parsing.definitions import (
    SUR_FIELDS,
    DEFAULT_SUR,
    DTIME_FIELDS,
    POS_NZ_FIELDS,
    DEFAULT_SUR_BODY,
    SUR_ARRAY_FIELDS,
)
from gdoes_analysis.parse_tools.general_tools import restructure_surf_dict

SUR_FMT = "<" + "".join(SUR_FIELDS.values())
SUR_HDR_SIZE = struct.calcsize(SUR_FMT)

DEFAULT_SUR_BODY_KEYS = set(DEFAULT_SUR_BODY.keys())
SUR_STRING_FIELDS = {k for k, v in SUR_FIELDS.items() if v.endswith("s")}
SUR_INT16_FIELDS = {k for k, v in SUR_FIELDS.items() if v == "h"}
SUR_INT32_FIELDS = {k for k, v in SUR_FIELDS.items() if v == "i"}
SUR_INT_FIELDS = SUR_INT16_FIELDS | SUR_INT32_FIELDS
SUR_FLOAT_FIELDS = {k for k, v in SUR_FIELDS.items() if v == "f"}

# %% SUR Loading


def clean_sur_dict(sur_dict: dict) -> dict:
    """
    Clean and structure a flat SUR dict:

    Parameters
    ----------
    sur_dict : dict
        Flat SUR dict as read by read_sur().
    Returns
    -------
    dict
        Cleaned and structured SUR dict.
    """
    out = sur_dict.copy()

    # --- 1. Timestamp → datetime ---
    try:
        out["timestamp"] = datetime(*(sur_dict.get(f, 0) for f in DTIME_FIELDS))
    except ValueError:
        out["timestamp"] = {k: out.get(k, 0) for k in DTIME_FIELDS}

    for k in DTIME_FIELDS:
        out.pop(k, None)

    # --- 2. Sub-groupings ---
    # group data, x_items, y_items, z_items, and t_items

    return restructure_surf_dict(out)


def read_sur(path: Path, raw=False, clean: bool = True) -> dict:
    """
    Read a SUR file into a flat dict.

    Parameters:
    ----------
    path : Path
        Path to the SUR file.
    raw : bool, optional
        If True, do not reshape points or build axes, by default False.
    Returns:
    -------
    dict
        Parsed SUR data.
    """
    data = path.read_bytes()
    mv = memoryview(data)

    # ---- 1. Unpack entire fixed header ----
    vals = struct.unpack_from(SUR_FMT, mv, 0)
    out = {}

    # ---- 2. Assign fields in order ----
    for k, v in zip(SUR_FIELDS.keys(), vals):
        if isinstance(v, (bytes, bytearray)):
            out[k] = v.split(b"\x00", 1)[0].decode("latin1")
        else:
            out[k] = v

    # ---- 3. Variable-length comment + private ----
    off = SUR_HDR_SIZE
    csize = out["comment_size"]
    psize = out["private_size"]

    out["comment"] = mv[off : off + csize].tobytes().split(b"\x00", 1)[0].decode("latin1")
    off += csize

    out["private"] = mv[off : off + psize].tobytes().split(b"\x00", 1)[0].decode("latin1")
    off += psize

    # ---- 4. Data block ----
    if out["size_of_points"] == 16:
        dtype = "<i2"
    elif out["size_of_points"] == 32:
        dtype = "<i4"
    else:
        raise ValueError("Unsupported size_of_points")

    nbytes = out["x_points"] * out["y_points"] * np.dtype(dtype).itemsize

    pts = np.frombuffer(mv[off : off + nbytes], dtype=dtype)

    if not raw:
        pts = pts.reshape((out["y_points"], out["x_points"]))

    pts = (pts - out["z_min"]) * out["z_spacing"] / out["z_unit_ratio"]
    # pts = (pts - out["z_min"]) * out["z_spacing"] + out["z_offset"]
    out["z_array"] = pts + out["z_offset"]

    # ---- 5. Axes ----
    out["x_array"] = (
        np.linspace(0, out["x_spacing"] * out["x_points"] / out["x_unit_ratio"], out["x_points"])
        + out["x_offset"]
    )
    out["y_array"] = (
        np.linspace(0, out["y_spacing"] * out["y_points"] / out["y_unit_ratio"], out["y_points"])
        + out["y_offset"]
    )

    if clean:
        out = clean_sur_dict(out)

    return out


def get_sur_df(path: Path, raw=False) -> pd.DataFrame:
    """
    Read a SUR file into a pandas DataFrame.

    Parameters
    ----------
    path : Path
        Path to the SUR file.
    raw : bool, optional
        If True, do not reshape points or build axes, by default False.
    Returns
    -------
    pd.DataFrame
        Parsed SUR data as a DataFrame.
    """
    sur_dict = read_sur(path, raw=raw, clean=True)
    data = sur_dict.pop("data", {})
    df = pd.DataFrame(data["z_array"], columns=data["x_array"], index=data["y_array"], dtype=float)
    df.attrs.update({k: v for k, v in sur_dict.items() if k != "z_array"})
    return df


# %% SUR Writing
def prepare_sur_dict(data: dict, **kwargs) -> dict:
    """
    Prepare a SUR-ready flat dict:

    Parameters
    ----------
    data : dict
        Input SUR data (possibly nested).
    kwargs : dict, optional
        Additional metadata to include in the output.
    Returns
    -------
    dict
        Flattened SUR dict ready for validation and writing.
    """

    # 1. Start from full SUR default (header + body)
    sur_data = DEFAULT_SUR.copy()

    # 2. Overlay caller-provided data
    sur_data |= data.copy()
    sur_data |= kwargs

    # 3. Expand any nested dicts (x_items, y_items, z_items, etc.)
    for key, value in data.items():
        if isinstance(value, dict):
            sur_data |= value
            sur_data.pop(key, None)

    # 4. Expand timestamp (clean_sur_dict form)
    ts = data.pop("timestamp", None)
    if isinstance(ts, datetime):
        sur_data.update(
            {
                "start_years": ts.year,
                "start_months": ts.month,
                "start_days": ts.day,
                "start_hours": ts.hour,
                "start_minutes": ts.minute,
                "start_seconds": ts.second,
                "start_week_day": ts.weekday(),
            }
        )

    return sur_data


def clean_sur_data(data: dict) -> tuple[dict, dict]:
    """
    Validate, coerce, and split SUR data into header/body dicts.

    Parameters
    ----------
    data : dict
        Flat SUR data dict.
    Returns
    -------
    tuple[dict, dict]
        (header dict, body dict)
    """
    header = {}
    body = {}

    for key in DEFAULT_SUR:
        # Use provided value or default
        value = data.get(key, DEFAULT_SUR[key])

        # String fields
        if key in SUR_STRING_FIELDS:
            if not isinstance(value, str):
                raise TypeError(f"{key} must be a string")

        # Integer fields
        elif key in SUR_INT_FIELDS:
            if isinstance(value, (int, float)):
                value = int(value)
            else:
                raise TypeError(f"{key} must be int or float-convertible")

        # Float fields
        elif key in SUR_FLOAT_FIELDS:
            if isinstance(value, (int, float)):
                value = float(value)
            else:
                raise TypeError(f"{key} must be float or int-convertible")

        # Array fields
        elif key in SUR_ARRAY_FIELDS:
            if isinstance(value, (list, tuple, np.ndarray, pd.Series, pd.DataFrame)):
                value = np.asarray(value)
            else:
                raise TypeError(f"{key} must be array-like")

        # Route to header or body
        if key in DEFAULT_SUR_BODY_KEYS:
            body[key] = value
        else:
            header[key] = value

    return validate_and_apply_geometry(header, body)


def validate_and_apply_geometry(header, data):
    """
    Validate and apply geometry to SUR data.

    Parameters
    ----------
    header : dict
        SUR header dict.
    data : dict
        SUR body dict.
    Returns
    -------
    tuple[dict, dict]
        (validated header dict, validated body dict)

    """
    try:
        points = np.squeeze(data["z_array"])

        # --- 0. Structural validation ---
        if points.ndim != 2:
            raise ValueError("points must be 2D")
        if points.size == 0:
            raise ValueError("points array is empty")

        Ny, Nx = points.shape  # allowed variables

        # --- 1. Validate / reconcile x_points, y_points ---
        Hx = header["x_points"]
        Hy = header["y_points"]

        if Hx and Hy:
            if Hx == Ny and Hy == Nx:
                points = points.T
                Ny, Nx = Nx, Ny
            elif Hx != Nx or Hy != Ny:
                raise ValueError("x_points/y_points contradict points shape")
        else:
            header["x_points"] = Nx
            header["y_points"] = Ny

        points = (points - header["z_offset"]) / header["z_spacing"]
        # points = (points - header["z_offset"]) * header["z_unit_ratio"] / header["z_spacing"]
        points += points.min().min()
        points -= points.max().max() / 2
        data["z_array"] = points.ravel(order="C")
        header["z_min"] = int(points.min())
        header["z_max"] = int(points.max())  # * header["z_unit_ratio"]
        # --- 2. Check items which require pos non-zero values ---

        # Validate positive non-zero integer values
        for field in POS_NZ_FIELDS:
            if header[field] <= 0:
                raise ValueError(f"{field} must be positive and non-zero")

        # --- 3. x_axis / y_axis handling ---

        # X‑axis offset/spacing
        x_axis = np.asarray(data.pop("x_array", np.array([])))
        if x_axis.size > 1:
            if len(x_axis) != Nx:
                raise ValueError("x_axis length mismatch")
            if x_axis[0]:
                if header["x_offset"] and header["x_offset"] != x_axis[0]:
                    raise ValueError("x_axis inconsistent with x_offset")
                header["x_offset"] = float(x_axis[0])

            space = (x_axis[-1] - x_axis[0]) * header["x_unit_ratio"] / Nx
            if header["x_spacing"] in {0, 1}:
                header["x_spacing"] = space
            else:
                if abs(header["x_spacing"] / space - 1) > 1e-6:
                    if abs(header["x_spacing"] / np.diff(x_axis).mean() - 1) <= 1e-6:
                        raise ValueError(
                            "x_unit_ratio inconsistent with x_spacing and x_axis (recommend setting x_unit_ratio=1.0)"
                        )
                    raise ValueError("x_axis inconsistent with x_spacing")

        # Y‑axis offset/spacing
        y_axis = np.asarray(data.pop("y_array", np.array([])))
        if y_axis.size > 1:
            if len(y_axis) != Ny:
                raise ValueError("y_axis length mismatch")
            if y_axis[0]:
                if header["y_offset"] and header["y_offset"] != y_axis[0]:
                    raise ValueError("y_axis inconsistent with y_offset")
                header["y_offset"] = float(y_axis[0])

            space = (y_axis[-1] - y_axis[0]) * header["y_unit_ratio"] / Ny
            if header["y_spacing"] in {0, 1}:
                header["y_spacing"] = space
            else:
                if abs(header["y_spacing"] / space - 1) > 1e-6:
                    if abs(header["y_spacing"] / np.diff(y_axis).mean() - 1) <= 1e-6:
                        raise ValueError(
                            "y_unit_ratio inconsistent with y_spacing and y_axis (recommend setting y_unit_ratio=1.0)"
                        )
                    raise ValueError("y_axis inconsistent with y_spacing")

        # --- 4. z_min/z_max ---
        # header["z_min"] = int(points.min())
        # header["z_max"] = int(points.max())
    except KeyError as exc:
        raise ValueError(f"Missing required SUR field: {exc}")

    return header, data


def to_sur(path: Path, data: dict, write_file: bool = True, **kwargs):
    """
    Create and write a SUR file from provided data.

    Parameters
    ----------
    path : Path
        Path to write the SUR file.
    data : dict
        SUR data dict (cleaned and structured).
    write_file : bool, optional
        Whether to write the SUR file, by default True.
    kwargs : dict, optional
        Additional metadata to include in the SUR file.

    Returns
    -------
    dict
        Info about the SUR writing process.
    """

    # 1. Flatten/prepare SUR dict
    sur_data = prepare_sur_dict(data, **kwargs)

    # 2. Validate, coerce, and split into header/body
    header, body = clean_sur_data(sur_data)

    # 3. Get scale and check size_of_points -> convert points
    scale = header["z_unit_ratio"] / header["z_spacing"]
    if header["size_of_points"] == 16:
        stored = body["z_array"].astype("<i2")
    elif header["size_of_points"] == 32:
        stored = body["z_array"].astype("<i4")
    else:
        raise ValueError("Unsupported size_of_points")

    # 4. Pack header
    packed = []
    for key, fmt in SUR_FIELDS.items():
        if fmt.endswith("s"):
            raw = str(header[key]).encode("latin1")
            n = int(fmt[:-1])
            packed.append(raw[:n].ljust(n, b"\x00"))
        else:
            packed.append(header[key])

    header_bytes = struct.pack(SUR_FMT, *packed)
    data_bytes = stored.tobytes(order="C")

    # 5. Write file (optional, default True)
    if write_file:
        path.write_bytes(header_bytes + data_bytes)

    # 6. Return info (for debugging)
    return {
        "header": header,
        "body": body,
        "scale": scale,
        "scaled_data": stored,
        "header_bytes": header_bytes,
        "data_bytes": data_bytes,
    }


if __name__ == "__main__":
    # N15_s2v2
    gd_folder = Path(
        r"D:\\Online\ASU Dropbox\Jacob Clenney\Work Docs\Data\Analysis\Profilometry\GDOES"
    )
    # res = read_sur(f_pth, clean=False)

    sur_res = read_sur(gd_folder / "N15_s2v5.sur")

    # res_df = get_sur_df(f_pth)

    # f_pth = Path(r"C:\\quantum") / str("data") / "2001-01/05/D0000276.sur"
    # res = read_sur(f_pth)
    # res_clean = clean_sur_dict(res)

    # o_pth = Path(r"C:\\Users\\j2cle\\Desktop\\D0000276_base.sur")
    # reversion0 = to_sur(o_pth, res_clean, write_file=True)
    # reloaded0 = read_sur(o_pth)

    # res_alt = res.copy()
    # res_alt["z_array"] = (res["z_array"] / 10).copy()
    # res_alt["z_offset"] = 0  # res["z_offset"] / 10

    # # no change
    # reversion1 = to_sur(o_pth.with_stem("D0000276_alt1"), res_alt, write_file=True)
    # reloaded1 = read_sur(o_pth.with_stem("D0000276_alt1"))

    # res_alt["z_spacing"] = res["z_spacing"] * 10
    # res_alt["z_unit_ratio"] = 1.0

    # # larger spacing
    # reversion2 = to_sur(o_pth.with_stem("D0000276_alt2"), res_alt, write_file=True)
    # reloaded2 = read_sur(o_pth.with_stem("D0000276_alt2"))

    # res_alt["z_spacing"] = res["z_spacing"]
    # res_alt["z_unit_ratio"] = 10.0

    # # larger unit ratio
    # reversion3 = to_sur(o_pth.with_stem("D0000276_alt3"), res_alt, write_file=True)
    # reloaded3 = read_sur(o_pth.with_stem("D0000276_alt3"))

    # res_alt["z_spacing"] = res["z_spacing"] * 10
    # res_alt["z_unit_ratio"] = 10.0

    # # larger spacing and unit ratio
    # reversion4 = to_sur(o_pth.with_stem("D0000276_alt4"), res_alt, write_file=True)
    # reloaded4 = read_sur(o_pth.with_stem("D0000276_alt4"))

    # res_alt["z_spacing"] = res_alt["z_spacing"]
    # res_alt["z_unit_ratio"] = 10.0

    # reversion1 = to_sur(o_pth.with_stem("D0000276_alt1"), res_alt, write_file=True)
    # reloaded1 = read_sur(o_pth.with_stem("D0000276_alt1"))

    # res_alt["z_spacing"] = res_alt["z_spacing"] * 10
    # res_alt["z_unit_ratio"] = 10.0

    # reversion1 = to_sur(o_pth.with_stem("D0000276_alt1"), res_alt, write_file=True)
    # reloaded1 = read_sur(o_pth.with_stem("D0000276_alt1"))
