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
Created on Mon Jan 19 11:19:11 2026
"""

# %% Imports
import re
from pathlib import Path
from datetime import datetime

import numpy as np

from gdoes_analysis.parse_tools.struct_tools import dyn_unpack, unpack_num_str, dyn_iter_unpack
from gdoes_analysis.prof_parsing.definitions import (
    TYPEID_INFO_MAP,
)
from gdoes_analysis.parse_tools.general_tools import (
    clean_bruker,
    eval_file_info,
    find_data_start,
    parse_axis_info,
    oldest_timestamp,
)

LENGTH_1_PREFIX = re.compile(rb"(?=([\x01-\x7f]))")
LENGTH_4_PREFIX = re.compile(rb"(?=([\x01-\x7f]\x00\x00\x00))")
INVALID = re.compile(r"[\uFFFD\x00-\x1F\x7F]")

SENTINEL = b"\x00\x00\x00\x00\x7f\xff\xff"

DIRECT_TYPES = {1, 6, 7, 11, 12, 13, 14}
EXTRA_TYPES = {19, 66}
VECTOR_TYPES = {64, 69, 124}
CONTAINER_TYPES = {70, 71, 125}
VALID_TYPEIDS = frozenset(TYPEID_INFO_MAP.keys())

SPECIAL_ENTRIES = {
    "Measurement",
    "ValueTypeName",
    "NumPoints",
    "Dimension1Points",
    "Dimension2Points",
    "SamplesToLog",
    "NumberOfTraces",
}

# %% OPDX tools


LENGTH_1_PREFIX = re.compile(rb"(?=([\x01-\x7f]))")
LENGTH_4_PREFIX = re.compile(rb"(?=([\x01-\xff]\x00\x00\x00))")


def find_next_opdx_section(
    data: bytes,
    offset: int = 0,
    *,
    max_name_len: int = 255,
    valid_ids: set | frozenset = VALID_TYPEIDS,
    encoding: str = "utf-8",
) -> int:
    """
    Locate the next valid section (default <I-sB>) starting at or after `offset`.

    Uses regex to jump to likely candidates, then validates each candidate
    by attempting unpack_num_str("<I-sB", ...). Returns the offset of the
    first valid section or the length of the data, signifying no valid section.
    """
    data_len = len(data)

    if offset + 5 > data_len:
        return data_len

    for p_match in LENGTH_4_PREFIX.finditer(data, offset):
        idx = p_match.start()
        # Bounds check
        if idx + 5 > data_len:
            break

        # Inline validation logic
        try:
            name_len, key, typeid = unpack_num_str(data, idx, others="B")
        except Exception:
            continue

        if typeid not in valid_ids or not key or not (1 <= name_len <= max_name_len):
            continue
        if INVALID.search(key.decode(encoding, errors="replace")):
            continue

        return idx

    return data_len


def find_next_opdx_section_old(
    data: bytes,
    offset: int = 0,
    pattern: re.Pattern = LENGTH_4_PREFIX,
    expected_typeid: int = -1,
    require_ascii: bool = True,
) -> int:
    """
    Locate the next valid <I-sB> section starting at or after `offset`.

    Uses regex to jump to likely candidates, then validates each candidate
    by attempting dyn_unpack("<I-aB", ...). Returns the offset of the first
    valid section or raises ValueError if none found.
    """

    n = len(data)

    if offset + 5 > n:
        raise ValueError(f"Buffer size too small for valid section after offset {offset}")

    valid_ids = {expected_typeid} if expected_typeid in VALID_TYPEIDS else VALID_TYPEIDS

    def _validate_res(start) -> bool:
        try:
            # name_len, key, typeid = dyn_unpack("<I-sB", data, start)
            name_len, key, typeid = unpack_num_str(data, start, others="B")
        except Exception:
            return False

        if typeid not in valid_ids:
            return False
        if not (1 <= name_len <= 200):
            return False
        if not key:
            return False
        if require_ascii and not all(32 <= b <= 126 for b in key):
            return False
        return True

    # 1) Fast path: try dyn_unpack directly at the given offset
    if offset and _validate_res(offset):
        return offset

    # 2) Regex-assisted search for the next candidate
    for m in pattern.finditer(data, offset):
        idx = m.start()
        if idx + 5 <= n and _validate_res(idx):
            return idx

    # # 3) raw fallback: scan byte-by-byte
    # for idx in range(offset, n - 5):
    #     try:
    #         length = struct.unpack_from("<I", data, idx)[0]
    #         # length = dyn_unpack("<I", data, idx)[0]
    #     except Exception:
    #         continue

    #     if not (1 <= length <= 200):
    #         continue

    #     if _validate_res(idx):
    #         return idx

    raise ValueError(f"No valid section found after offset {offset}")


def _extend_names(vals, names=tuple(), prefix="other") -> dict:
    result = {}
    vals = list(vals)
    names = list(names)
    names += [f"{prefix}_{i}" for i in range(len(vals) - len(names))]
    for name, value in zip(names, vals):
        result[name] = value
    return result


# def dyn_iter_unpack(fmt, data, pos, end=0, return_pos=False):
#     """
#     Generic iterative unpacker.
#     """
#     values = []
#     cur = pos
#     stop = end if end > 0 else len(data)

#     while cur < stop:
#         try:
#             out = dyn_unpack(fmt, data, cur, return_pos=True)
#         except ValueError:
#             break

#         values.extend(out[:-1])
#         cur = out[-1]

#     if return_pos:
#         values.append(cur)

#     return values, data[cur:stop]


def _filter_unpacked_meta(key: str) -> bool:
    """Determine if a key is metadata to be filtered out."""
    if key == "byte_width":
        return False
    if key.startswith("other_"):
        return False
    if key.endswith("_len"):
        return False
    return True


# %% OPDX parsers


def parse_opdx_defined_payload(node, data, pos, info: dict):
    """
    Parse payload using the type's defined payload_fmt.
    This is NOT a fallback parser. Missing fmt is an error.
    """

    typeid = node["typeid"]
    type_info = TYPEID_INFO_MAP[typeid]
    payload_fmt = type_info[2].strip().replace(" ", "")
    include_meta = info.get("include_meta", False)

    if not payload_fmt or (len(payload_fmt) == 1 and payload_fmt[0] in "<>=!@"):
        raise ValueError(
            f"typeid {typeid} has no payload_fmt but parse_opdx_defined_payload was called"
        )

    # --- Parse using dyn_unpack
    parsed = dyn_unpack(payload_fmt, data, pos, return_pos=True, return_fmt=True)
    stop = parsed[-2]

    if include_meta:
        node["fmt"] = parsed[-1]
        node["payload_stop"] = stop

    # --- Extract values
    p_vals = parsed[:-2]
    names = list(type_info[3])

    # --- Strict name/value count match
    if len(p_vals) == len(names):
        for name, value in zip(names, p_vals):
            if include_meta or _filter_unpacked_meta(name):
                node[name] = value
    else:
        # Mismatch → store raw list
        node["parsed"] = p_vals

    return node, stop


def parse_opdx_basic(node, data, pos, info: dict):

    try:
        node, pos = parse_opdx_defined_payload(node, data, pos, info)
    except ValueError as exc:
        print(f"Warning: failed to parse vector typeid {node['typeid']} at pos {pos}: {exc}")

    stop = find_next_opdx_section(data, pos)

    if pos != stop:
        node["raw"] = data[pos:stop]

    return node, stop


def parse_opdx_string(node, data, pos, info: dict):
    """
    Placeholder for types with special parsing not yet implemented.
    Returns the next valid section offset.
    """

    node, next_pos = parse_opdx_defined_payload(node, data, pos, info)
    val = node.pop("text", "").strip()
    if not val:
        node["value"] = val
        return node, next_pos

    try:
        if re.match(r"^\d{4}/\d{2}/\d{2} \d{2}:\d{2}:\d{2}\.\d+$", val):
            val = datetime.strptime(val, "%Y/%m/%d %H:%M:%S.%f")
        elif re.match(r"^\d/\d{1,2}/\d{4}$", val):
            val = datetime.strptime(val, "%m/%d/%Y").date()
        elif re.match(r"^\d\d?:\d{2}:\d{2} [ap]m$", val, re.I):
            val = datetime.strptime(val, "%I:%M:%S %p").time()
        else:
            val = eval(val) if val.lower() != "nan" else float("nan")
    except (ValueError, NameError, SyntaxError):
        pass  # Return raw string if parsing fails

    node["value"] = val

    return node, next_pos


def parse_opdx_datetime(node, data, pos, info: dict):
    """
    Placeholder for types with special parsing not yet implemented.
    Returns the next valid section offset.
    """
    next_pos = find_next_opdx_section(data, pos)

    if info.get("include_meta", False):
        raw = data[pos:next_pos]
        node["raw"] = raw
        node["parsed"] = list(raw)
    else:
        node["value"] = datetime.now()

    return node, next_pos


def parse_opdx_extra(node, data, pos, info: dict):
    """
    Parse a repeating pattern until the next section.
    fmt is hard-coded here; you will insert your own if/else above it.
    """
    include_meta = info.get("include_meta", False)

    node, pos = parse_opdx_defined_payload(node, data, pos, info)
    stop = find_next_opdx_section(data, pos)

    if node["typeid"] == 19:
        if "parsed" in node and len(node["parsed"]) == 6:
            names = (
                "byte_width",
                "header_len",
                "value",
                "ascii_len",
                "utf_len",
                "unit_multiplier",
            )
            for name, value in zip(names, node.pop("parsed", [])):
                if include_meta or _filter_unpacked_meta(name):
                    node[name] = value

        values, residual = dyn_iter_unpack("<I", data, pos, stop)
        if include_meta:
            if values:
                node["flags"] = values
            if residual:
                node["raw"] = residual
    elif node["typeid"] == 66:
        values, residual = dyn_iter_unpack("<I-u", data, pos, stop)
        if values:
            names = _extend_names([values[i] for i in range(1, len(values), 2)], prefix="value")
            node |= names
        if include_meta and residual:
            node["raw"] = residual
    else:
        node["undefined"] = [r for r in data[pos:stop]]

    return node, stop


def parse_opdx_container(node, data, pos, info: dict):
    """
    Parse a container section.
    node: partially filled node dict
    pos: start of container payload
    parsed_header: list of parsed header values (parsed[:-2])
    """
    include_meta = info.get("include_meta", False)
    node, pos = parse_opdx_defined_payload(node, data, pos, info)

    end = pos + node["byte_size"]

    sentinel_start = end - len(SENTINEL)
    if data[sentinel_start:end] != SENTINEL:
        raise ValueError(f"Container '{node['key']}' missing sentinel at offset {sentinel_start}")

    if include_meta:
        node["payload_stop"] = sentinel_start
        node["section_stop"] = end

    # Clip recursion to container payload only
    while pos < sentinel_start:
        child, pos = parse_opdx_section(data[:sentinel_start], pos, info)

        key = child.get("key", "unknown")
        typeid = child.get("typeid", -1)

        if not include_meta:
            child.pop("key", "unknown")
            child.pop("typeid", -1)
            child.pop("byte_size", None)
            node[key] = child

        if len(child) == 1:
            child_val = next(iter(child.values()))
            if typeid in CONTAINER_TYPES and not isinstance(child_val, dict):
                node[key] = {}
            else:
                node[key] = child_val
        else:
            node[key] = child

    return node, end


def parse_opdx_section(data: bytes, offset: int, info: dict):
    """
    Parse a single section header, then dispatch to the correct payload parser.
    """
    # --- 1) Parse header
    # _, key, typeid, pos = dyn_unpack("<I-aB", data, offset, return_pos=True)
    _, key, typeid, pos = unpack_num_str(data, offset, str_fmt="a", others="B", return_pos=True)

    node = {"key": key, "typeid": typeid}

    type_info = TYPEID_INFO_MAP.get(typeid)
    if not type_info:
        raise ValueError(f"Unknown typeid {typeid} at offset {offset}")

    if info.get("include_meta", False):
        node["tag"] = type_info[0]
        node["section_start"] = offset
        node["payload_start"] = pos

    # --- 2) Dispatch to container parser
    if typeid in CONTAINER_TYPES:
        return parse_opdx_container(node, data, pos, info)

    # --- 3) Dispatch to other parsers
    if typeid in DIRECT_TYPES:
        node, pos = parse_opdx_defined_payload(node, data, pos, info)
        # node, pos = parse_opdx_direct(node, data, pos, info)

    elif typeid in EXTRA_TYPES:
        node, pos = parse_opdx_extra(node, data, pos, info)

    elif typeid in VECTOR_TYPES:
        info["vectors"][key] = node
        node, pos = parse_opdx_basic(node, data, pos, info)
        if node.get("raw") is None:
            raise ValueError(f"Vector '{key}' has no raw data at offset {pos}")

    elif typeid == 18:
        node, pos = parse_opdx_string(node, data, pos, info)

    elif typeid == 21:
        node, pos = parse_opdx_datetime(node, data, pos, info)

    else:
        node, pos = parse_opdx_basic(node, data, pos, info)

    if key in SPECIAL_ENTRIES:
        info[key] = node.get("text", node.get("value", None))

    if info.get("include_meta", False):
        node["payload_stop"] = pos
        node["section_stop"] = pos

    return node, pos


def post_parse_opdx_vectors(node, raw, info: dict):
    include_meta = info.get("include_meta", False)
    num_points, byte_length = parse_axis_info(len(raw), info)

    if len(raw) / byte_length != num_points:
        header = find_data_start(raw, 0, byte_length)
        byte_length = header.pop("byte_length", byte_length)
        raw = header.pop("data", raw)
        node |= {k: v for k, v in header.items() if include_meta or _filter_unpacked_meta(k)}

    dtype = np.float64 if byte_length == 8 else np.float32
    node["data"] = np.frombuffer(raw, dtype=dtype)

    if info["is_2d"]:
        node["data"] = node["data"].reshape((info["Nx"], info["Ny"]))

    if not include_meta:
        node.pop("byte_length", None)
        node.pop("byte_size", None)
        node.pop("data_offset", None)

    return node


def read_bruker_opdx(
    path: Path | str,
    include_meta: bool = False,
    clean: bool = True,
    header_encoding: str = "ascii",
    parse_arrays: bool = True,
    **kwargs,
) -> dict:
    path = Path(path)
    raw = path.read_bytes()

    root = {}
    root["filename"] = path.name
    root["path"] = str(path)
    root["timestamp"] = oldest_timestamp(path)

    offset = find_next_opdx_section(raw, 0, encoding=header_encoding)
    if offset >= len(raw):
        return root

    if offset > 0:
        data = raw[offset : -len(SENTINEL)] if raw.endswith(SENTINEL) else raw[offset:]
        root["pre_header_bytes"] = raw[:offset]
        root["pre_header_len"] = offset
        offset = 0
    else:
        data = raw

    n_data = len(data)
    info = {}
    info["include_meta"] = include_meta
    info["vectors"] = {}
    while offset < n_data:
        node, offset = parse_opdx_section(data, offset, info)
        root[node["key"]] = node

    root |= kwargs

    eval_file_info(info, format_name="bruker-xml", def_2d="Raw" in root["2D_Data"])

    if parse_arrays:
        for vector in info["vectors"].values():
            raw_vector = vector.pop("raw", b"")
            post_parse_opdx_vectors(vector, raw_vector, info)

    if not include_meta:
        # root = {k: v for k, v in root.items() if isinstance(v, dict)}
        # if not include_meta and any(isinstance(v, dict) for v in node.values()):
        for child in root.values():
            if isinstance(child, dict):
                child.pop("key", None)
                child.pop("typeid", None)
                child.pop("byte_size", None)

        if clean:
            root = clean_bruker(root)

    return root


# %% Example usage
if __name__ == "__main__":
    # Example usage
    gd_folder = Path(
        r"D:\\Online\ASU Dropbox\Jacob Clenney\Work Docs\Data\Analysis\Profilometry\GDOES"
    )

    d1_parsed = read_bruker_opdx(gd_folder / "evap_prof_3.OPDx")

    d2_parsed = read_bruker_opdx(gd_folder / "N15_s2.OPDx")

    d1_parsed_raw = read_bruker_opdx(gd_folder / "evap_prof_3.OPDx", include_meta=True)

    d2_parsed_raw = read_bruker_opdx(gd_folder / "N15_s2.OPDx", include_meta=True)
