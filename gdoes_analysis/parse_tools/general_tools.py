import re
import struct
from typing import Any
from pathlib import Path
from datetime import datetime

import numpy as np

from gdoes_analysis.prof_parsing.definitions import PRIORITY_META, BRUKER_RENAME_MAP

# ---- General purpose parsing tools ---- #


def combine_keys(*args):
    """
    Combines multiple keys into a tuple, flattening nested tuples/lists and filtering out invalid entries.
    """
    flat_args = []
    for arg in args:
        if isinstance(arg, (tuple, list)):
            flat_args.extend(tuple(arg))  # Flatten nested tuples/lists
        else:
            flat_args.append(arg)  # Add single keys directly
    # Filter out invalid entries (e.g., None or non-string types)
    return tuple([f_arg for f_arg in flat_args if isinstance(f_arg, str) and f_arg])


def flatten_dict(
    arg: dict,
    parent_key: str | tuple = "",
    sep: str | object = "/",
) -> dict:
    """
    Flattens a nested dictionary into a single dictionary, combining keys with a specified separator
    or as a tuple if sep is not a string.

    Parameters:
    - arg (dict): The nested dictionary to flatten.
    - parent_key (str or tuple, optional): The base key for the current level. Default is an empty string.
    - sep (str or any, optional): The separator to use for combining keys. If not a string, keys are returned as tuples.

    Returns:
    - dict: The flattened dictionary.
    """
    if not isinstance(arg, dict):
        return arg

    items = []
    for k, v in arg.items():
        if isinstance(sep, str):
            new_key = f"{parent_key}{sep}{k}" if parent_key else k
        else:
            new_key = combine_keys(parent_key, k)

        if isinstance(v, dict):
            items.extend(flatten_dict(v, new_key, sep=sep).items())
        else:
            items.append((new_key, v))
    return dict(items)


def oldest_timestamp(path: str | Path) -> datetime:
    """Get the older timestamp (creation or modification) of a file."""
    st = Path(path).stat()
    birth = getattr(st, "st_birthtime", None)

    # choose the older of the two that exist
    if birth is None:
        return datetime.fromtimestamp(st.st_mtime)
    return datetime.fromtimestamp(min(birth, st.st_mtime))


# ---- Format-specific cleaning tools ---- #


def find_data_start(data: bytes, offset: int = 0, byte_len: int = 0) -> dict:
    """Parse header of 1D Vector data."""
    header = {}
    d_len = len(data)

    # 4) Flags (int32 list)
    header["flags"] = []

    b_vals = [8, 4] if byte_len == 0 else [byte_len]
    for loc in range(offset, d_len, 4):
        val = struct.unpack_from("<i", data, loc)[0]
        for b_len in b_vals:
            # len - (loc + 4 (for int32) + val * b_len (expected len if val is count))
            if d_len - loc - 4 - val * b_len < 8:
                header["byte_length"] = b_len
                header["x_points"] = val
                h_len = d_len - val * b_len
                header["data"] = data[h_len:]
                return header

        header["flags"].append(val)

    raise ValueError("Unable to parse 1D Vector header")


def restructure_surf_dict(raw_dict: dict) -> dict:
    """
    Restructures a parsed dictionary into a standardized format.

    Parameters
    ----------
    raw_dict : dict
        The parsed Bruker file dictionary from decode_types().
    Returns
    -------
    dict
        A restructured dictionary.
    """
    out = {}
    out["data"] = {}
    for key in ["x_array", "y_array", "z_array"]:
        if key in raw_dict:
            out["data"][key] = raw_dict.pop(key, None)

    out["data_info"] = {}
    for key in list(raw_dict.keys()):
        if key.startswith(("z_", "x_", "y_")):
            out["data_info"][key] = raw_dict.pop(key, None)

    for k in PRIORITY_META:
        if k in raw_dict:
            out[k] = raw_dict.pop(k, None)

    if raw_dict:
        out["other_metadata"] = raw_dict.copy()

    return out


def eval_file_info(info: dict, format_name: str = "bruker", def_2d: bool = False) -> dict:

    if "standard" in info.get("Measurement", "").lower():
        info["source_format"] = f"{format_name}: standard (1d)"
        info["is_2d"] = False
        try:
            info["num_points"] = int(info.get("NumPoints", 0))
        except (ValueError, TypeError, KeyError):
            info["num_points"] = 0

    elif "map" in info.get("Measurement", "").lower():
        info["source_format"] = f"{format_name}: map (2d)"
        info["is_2d"] = True
        try:
            info["Nx"] = int(info.get("Dimension1Points", 0))
            info["Ny"] = int(info.get("Dimension2Points", 0))
            info["num_points"] = info["Nx"] * info["Ny"]
        except (KeyError, ValueError, TypeError):
            info["Nx"] = info["Ny"] = info["num_points"] = 0

    else:
        info["source_format"] = f"{format_name}: unknown"
        info["is_2d"] = def_2d
        info["num_points"] = info.get("NumPoints", 0)

    # ValueTypeName
    info.setdefault("ValueTypeName", "single")
    if "double" in info["ValueTypeName"].lower():
        info["data_dtype"] = "float64"
        info["byte_length"] = 8
    else:
        info["data_dtype"] = "float32"
        info["byte_length"] = 4

    return info


def parse_axis_info(d_len: int, info: dict | None, source: str = "") -> tuple[int, int]:
    """
    Determine number of points and byte length per point for axis data.

    Parameters
    ----------
    d_len : int
        Total length of the data in bytes.
    info : dict, optional
        Additional information about the data.
    source : str
        Source type (e.g., "Matrix", "Array").

    Returns
    -------
    tuple
        A tuple containing the number of points and byte length per point.
    """
    byte_length = 0
    num_points = 0
    if info:
        as_2d = info["is_2d"]
        num_points = info["num_points"]
        if num_points > 0:
            byte_length = d_len / num_points
            if byte_length not in (4, 8):
                if info["data_dtype"] == "float32":
                    byte_length = 4
                elif info["data_dtype"] == "float64":
                    byte_length = 8
                else:
                    byte_length = 0
    else:
        as_2d = "matrix" in source.lower()
        byte_length = 4 if as_2d else 8

    if num_points and not byte_length:
        byte_length = d_len // num_points
        if byte_length not in (4, 8):
            # Choose the most likely dtype based on smallest mismatch
            delta_8 = d_len - num_points * 8
            delta_4 = d_len - num_points * 4
            if delta_8 < 0 and delta_4 < 0:
                raise ValueError("Not enough bytes for specified num_points")
            byte_length = 8 if 0 <= delta_8 < delta_4 else 4

    return num_points, byte_length


def clean_bruker(raw_dict: dict, fmt_name: str = "bruker") -> dict:
    """
    Cleans and restructures a parsed Bruker file dictionary.

    Parameters
    ----------
    raw_dict : dict
        The parsed Bruker file dictionary from decode_types().
    Returns
    -------
    dict
        A cleaned and restructured dictionary.
    """
    flt_dict: dict[str, Any] = flatten_dict(raw_dict, sep=".")
    flt_dict = {BRUKER_RENAME_MAP.get(k, k): v for k, v in flt_dict.items()}

    # if "two_d_block" in flt_dict and flt_dict["two_d_block"] is None:
    if "standard" in flt_dict["measurement"].lower():
        flt_dict["source_format"] = f"{fmt_name}: standard (1d)"
        flt_dict["z_array"] = flt_dict["data"] * flt_dict["z_scale"]

    # elif "one_d_block" in flt_dict and flt_dict["one_d_block"] is None:
    elif "map" in flt_dict["measurement"].lower():
        flt_dict["source_format"] = f"{fmt_name}: map (2d)"
        flt_dict["x_scale"] = flt_dict["x_max"] / flt_dict["x_points"]
        flt_dict["y_scale"] = flt_dict["y_max"] / flt_dict["y_points"]
        flt_dict["x_array"] = np.arange(0, flt_dict["x_points"]) * flt_dict["x_scale"]
        flt_dict["y_array"] = np.arange(0, flt_dict["y_points"]) * flt_dict["y_scale"]
        flt_dict["z_array"] = flt_dict["data"] * flt_dict["z_scale"]

    return restructure_surf_dict(flt_dict)


# ---- Retired OPDx paring tools adapted for general use ---- #


def iter_ascii_regions(
    data: bytes, min_len: int = 3, prefix: bytes = b""
) -> tuple[list[dict], list[dict]]:
    """
    Locate ASCII-prefixed entries using regex as a coarse anchor.
    """
    n_data = len(data)
    results = []
    skipped = []

    if not prefix:
        r_prefix = re.compile(rb"(?=([\x01-\x7f]\x00\x00\x00))")
    else:
        r_prefix = re.compile(prefix)

    for m in r_prefix.finditer(data):
        res = {"len": 0, "b_str": b"", "start": 0, "stop": 0}
        start = res["start"] = m.start()

        # 1) Read <i length>
        try:
            length = res["len"] = struct.unpack_from("<i", data, start)[0]
        except struct.error:
            skipped.append(res)
            continue

        if not (1 <= length <= 200):  # safe upper bound
            skipped.append(res)
            continue

        ascii_start = start + 4  # start of ascii
        ascii_end = res["stop"] = ascii_start + length  # end of ascii

        if ascii_end > n_data:
            skipped.append(res)
            continue

        ascii_bytes = res["b_str"] = data[ascii_start:ascii_end]

        # 2) Validate ASCII: full printable range
        if not all(32 <= b <= 126 for b in ascii_bytes):
            skipped.append(res)
            continue

        if min_len > length:  # safe upper bound
            skipped.append(res)
            continue

        # 3) Return structural info only
        results.append(res)
    return results, skipped


def absorb_skipped(results, skipped, data):
    """
    Merge skipped entries into the previous valid result when they are
    contiguous in the file.
    """
    if not results or not skipped:
        return results

    # Map skipped entries by their start offset
    skip_by_start = {s["start"]: s for s in skipped}

    for res in results:
        # Try to absorb multiple chained skipped entries
        while res["stop"] in skip_by_start:
            sk = skip_by_start[res["stop"]]

            # Extend stop to include the skipped region
            res["stop"] = sk["stop"]

            # Re-slice data to ensure no bytes are lost
            res["data"] = data[res["start"] + len(res["prefix"]) : res["stop"]]

    return results


def extract_typeid_and_payload(regions, data):
    """
    Takes the valid list from iter_ascii_regions and extracts typeid and data payload.
    """
    n_data = len(data)
    n_reg = len(regions)

    results = []
    skipped = []
    sort_reg = sorted(regions, key=lambda r: r["start"])

    for i, r in enumerate(sort_reg):
        res = {
            "name": "",  # Decoded ASCII name of section
            "typeid": 0,  # Section type identifier (int)
            "prefix": b"",  # Section prefix bytes: ascii length + ascii (+ typeid)
            "data": b"",  # Section data bytes
            "start": r["start"],  # start offset of section in original data (includes prefix)
            "stop": r["stop"],  # stop offset of section in original data (updated to include data)
        }

        # name
        res["name"] = r["b_str"].decode("ascii", errors="replace")
        res["prefix"] = data[r["start"] : r["stop"]]

        # typeid offset
        typeid_offset = r["stop"]
        if typeid_offset >= n_data:
            skipped.append(res)
            continue

        # typeid
        try:
            res["typeid"] = struct.unpack_from("<B", data, typeid_offset)[0]
        except struct.error:
            skipped.append(res)
            continue
        res["prefix"] += data[typeid_offset : typeid_offset + 1]

        # data region (excludes ascii and typeid byte)
        # start = after typeid byte (which is after ascii)
        data_start = typeid_offset + 1
        if i + 1 < n_reg:
            data_stop = res["stop"] = sort_reg[i + 1]["start"]  # stop = start of next ascii
        else:
            data_stop = res["stop"] = n_data

        if data_stop < data_start:
            skipped.append(res)
            continue

        res["data"] = data[data_start:data_stop]

        results.append(res)

    results = absorb_skipped(results, skipped, data)

    return results, skipped


def filter_by_typeid_and_name(entries, typeid_map, data):
    """
    Filter entries by comparing typeid and name against a provided map.
    """
    valid = []
    skipped = []

    for e in entries:
        tid = e["typeid"]
        name = e["name"]

        # typeid must exist AND name must be in its allowed set
        if tid in typeid_map and name in typeid_map[tid]:
            valid.append(e)
        else:
            skipped.append(e)

    valid = absorb_skipped(valid, skipped, data)

    return valid, skipped


def summary_print(entries, *keys, byte_length=10, sort_by="name"):
    """
    Print a summary of entries.
    """
    if not entries:
        print("No entries to summarize.")
        return
    if not keys:
        keys = ("typeid", "len", "name")

    c_map = {"len": lambda data, **_: len(data)}

    p_map = {
        "name": ("Name: ", lambda name, **_: f"{name}\t"),
        "typeid": ("ID: ", lambda typeid, **_: f"{typeid}\t" if typeid < 10 else f"{typeid}\t"),
        "data": (f"Data[:{byte_length}]: ", lambda data, **_: f"{data[:-4][:byte_length]}\t"),
        "start": ("Start: ", lambda start, **_: f"{start}\t"),
        "stop": ("Stop: ", lambda stop, **_: f"{stop}\t"),
        "len": (
            "Length: ",
            lambda data, **_: f"{len(data)}\t\t\t" if len(data) < 100 else f"{len(data)}\t",
        ),
        "delta": (
            "Delta: ",
            lambda start, stop, **_: (
                f"{stop - start}\t\t" if (stop - start) < 100 else f"{stop - start}\t"
            ),
        ),
        "delta_err": (
            "Delta_Err: ",
            lambda start, stop, data, **_: (
                f"{(stop - start) - len(data)}\t\t"
                if ((stop - start) - len(data)) < 100
                else f"{(stop - start) - len(data)}\t"
            ),
        ),
    }

    for e in sorted(entries, key=lambda r: r.get(sort_by, c_map.get(sort_by, c_map["len"])(**r))):
        print(*[p_map[k][0] + p_map[k][1](**e) for k in keys])


def rebuild_parsed_tree(parsed_data, container_types={70, 71, 125}):
    """
    Build a nested structure of parsed values using only parsed_data
    and the key metadata (i, name, typeid, start, stop, fmt).

    Output node structure:
        {
            "children": { (i,name): node, ... },
            "typeid": typeid,
            "start": start,
            "fmt": fmt,
            "parsed": parsed_list
        }
    """

    # Convert dict → list of (key, parsed)
    items = [(key, parsed) for key, parsed in parsed_data.items()]

    # Sort by start offset
    items.sort(key=lambda x: x[0][3])  # key[3] = start

    # Root node (virtual container)
    root = {
        "children": {},
        "typeid": None,
        "start": None,
        "fmt": None,
        "parsed": None,
        "full_key": None,
    }
    stack = [root]

    for key, parsed in items:
        i, name, typeid, start, stop, fmt = key

        node = {
            "children": {},
            "typeid": typeid,
            "start": start,
            "fmt": fmt,
            "parsed": parsed,
            "full_key": key,  # <-- store full key here
        }

        # Find correct parent by byte-range containment
        while len(stack) > 1:
            parent = stack[-1]
            parent_key = parent["full_key"]

            if parent_key is None:
                break

            _, _, p_typeid, p_start, _, _ = parent_key

            if p_typeid in container_types:
                p_len = parsed_data[parent_key][1]  # container length
                p_stop = p_start + p_len
            else:
                p_stop = p_start

            if p_start <= start <= p_stop + 3:
                break

            stack.pop()

        # Attach to current parent
        stack[-1]["children"][(i, name)] = node

        # If this is a container, push it
        if typeid in container_types:
            stack.append(node)

    # Remove helper "key" fields from nodes
    def strip(node):
        node.pop("key", None)
        if not node["children"]:
            node.pop("children")
        else:
            for child in node["children"].values():
                strip(child)

    strip(root)

    return root
