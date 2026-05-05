import re
import gzip
import base64
import struct
import warnings
import xml.etree.ElementTree as ET
from typing import Any
from pathlib import Path
from datetime import date, time, datetime
from collections import defaultdict

import numpy as np

from gdoes_analysis.prof_parsing.definitions import TYPEID_INFO_MAP, BRUKER_RENAME_MAP
from gdoes_analysis.parse_tools.general_tools import (
    clean_bruker,
    eval_file_info,
    parse_axis_info,
    oldest_timestamp,
)

REVISED_NAMES = set(BRUKER_RENAME_MAP.values())

SPECIAL_ENTRIES = {
    "Measurement",  # both
    "ValueTypeName",  # 1d
    "NumPoints",  # 1d
    "Dimension1Points",  # 2d
    "Dimension2Points",  # 2d
    "SamplesToLog",  # both
    "NumberOfTraces",  # both
}

DIRECT_TYPES = {1, 6, 7, 11, 12, 13, 18, 21}
VECTOR_TYPES = {64, 69}  # 124
CONTAINER_TYPES = {70, 71, 125}

# %% --- Parse XML tree into nested dict ---


def _parse_bruker_node(node, info: dict | None = None) -> tuple[dict, dict]:
    """
    Recursively parse a DigitalSurf XML node into a nested dictionary.

    Parameters
    ----------
    node : xml.etree.ElementTree.Element
        The XML node to parse.
    info : dict, optional
        A dictionary to accumulate special entries.

    Returns
    -------
    tuple
        A tuple containing the parsed node as a dictionary and the accumulated info dictionary.
    """
    if info is None:
        info = {}

    # Base entry: tag + attributes
    entry = {"tag": node.tag}
    entry.update(node.attrib)

    # Normalize typeid
    if "typeid" in entry:
        try:
            entry["typeid"] = int(entry["typeid"])
        except (ValueError, TypeError):
            pass

    # Parse children
    results: list[tuple[dict, ...]] = list(zip(*[_parse_bruker_node(c, info=info) for c in node]))
    raw_children, infos = results if list(node) else [tuple(), ({},)]

    for c_info in infos:
        info |= c_info

    # If no children, treat as leaf
    if not raw_children:
        entry["text"] = node.text if node.text is not None else "Nan"
        if entry.get("key", "") in SPECIAL_ENTRIES:
            info[entry["key"]] = entry["text"]
        return entry, info

    # Determine whether child tags are unique
    tags = [c["tag"] for c in raw_children]
    if len(tags) != len(set(tags)):
        tags = [f"child{i}: {t}" for i, t in enumerate(tags)]

    children = {}
    all_dicts = True
    unique_keys = True
    for child, tag in zip(raw_children, tags):
        if len(child) == 2:
            key = tag
            child.pop("tag", None)
            children[key] = next(iter(child.values()))
        else:
            key = child.pop("key", tag)
            children[key] = child

        all_dicts &= isinstance(children[key], dict)
        unique_keys &= key not in entry

    if all_dicts:
        entry["children"] = children
    elif unique_keys:
        entry |= children

    return entry, info


# %% --- Decode typed nodes ---


def parse_xml_named_data(node, **kwargs) -> dict:
    """Parse a Named Data node (typeid 14)."""
    return {
        "typename": node.get("typename", ""),
        "value": parse_xml_string(node, **kwargs),
    }


def parse_xml_string(node, source="", **kwargs) -> bool | int | float | str | date | time:
    """Parse a string node (typeid 18)."""
    val = node.get("text", node.get("Value", kwargs.get("_default", "")))

    if not isinstance(val, str):
        return val

    if "date" in source.lower() or "time" in source.lower():
        return parse_datetime({"text": val}, source=source, **kwargs)

    try:
        return eval(val) if val.strip().lower() != "nan" else float("nan")
    except (NameError, SyntaxError):
        pass

    return str(val).strip()


def parse_xml_unit_value(node, **kwargs) -> dict[str, int | float]:
    """Parse a Unit-Value pair node (typeid 19)."""
    try:
        val = eval(node["Value"]) if node["Value"].strip().lower() != "nan" else float("nan")
        res = {"unit_name": node.get("Unit", "unitless"), "value": val}
    except (NameError, SyntaxError):
        inv_val = node["Value"]
        raise ValueError(f"Invalid Unit-Value structure. Unable to parse value {inv_val}")

    if not res["unit_name"] or res["unit_name"].lower() == "nan":
        res["unit_name"] = kwargs.get("default_unit", "unitless")
    return res


def parse_datetime(node, **kwargs) -> datetime | date | time | str:
    """Parse a DateTime node (typeid 21)."""
    val = node.get("text", node.get("Value", kwargs.get("_default", "")))
    try:
        if re.match(r"^\d{4}/\d{2}/\d{2} \d{2}:\d{2}:\d{2}\.\d+$", val):
            return datetime.strptime(val, "%Y/%m/%d %H:%M:%S.%f")
        if re.match(r"^\d/\d{1,2}/\d{4}$", val):
            return datetime.strptime(val, "%m/%d/%Y").date()

        if re.match(r"^\d\d?:\d{2}:\d{2} [ap]m$", val, re.I):
            return datetime.strptime(val, "%I:%M:%S %p").time()
    except ValueError:
        pass  # Return raw string if parsing fails
    return val


def parse_xml_str_vector(node, **kwargs) -> str:
    """Parse a String Vector node (typeid 66)."""

    strs = node.get("Str", node.get("text", node.get("Value", kwargs.get("_default", ""))))
    return str(strs)


def parse_xml_container(node, source="", **kwargs) -> dict | None:
    """Parse a Container node (typeid 70, 71, 125)."""
    res = node.get("children", kwargs.get("_default"))
    if res is None:
        if "d_channels" in source.lower():
            return {"Height": None}
    return res


def parse_xml_pos_function(node, **kwargs):
    """Parse a Position Function node (typeid 124)."""
    if "children" in node:
        children = {}
        for key, child in node["children"].items():
            children[key] = parse_xml_unit_value(child, **kwargs)
        return children
    if "encoding" in node:
        return parse_xml_data_array(node, **kwargs)
    return node


def parse_header_2d_matrix(data: bytes, body_points: int, byte_length: int) -> dict:
    """Parse header of 2D Matrix data."""
    x, y = struct.unpack_from("<ii", data, 0)
    return {
        "x_points": x,
        "y_points": y,
        "byte_length": byte_length or 4,
        "total_points": body_points,
        "data": data[8:],
    }


def parse_header_1d_data(data: bytes, body_points: int, byte_length: int) -> dict:
    """Parse header of 1D Data array."""
    data_offset, stored_len = struct.unpack_from("<bi", data, 0)

    if not byte_length:
        byte_length = stored_len if stored_len in (4, 8) else 8

    if not body_points:
        body_points = (len(data) - 5) // byte_length

    return {
        "data_offset": data_offset,
        "byte_length": byte_length,
        "z_points": body_points,
        "data": data[len(data) - body_points * byte_length :],
    }


def parse_header_1d_vector(data: bytes, body_points: int, byte_length: int) -> dict:
    """Parse header of 1D Vector data."""
    header = {}
    offset = 0
    d_len = len(data)
    h_len = d_len - body_points * byte_length

    # 1) ASCII unit name
    ascii_len = struct.unpack_from("<i", data, offset)[0]
    offset += 4
    header["unit_name"] = data[offset : offset + ascii_len].decode("ascii", errors="replace")
    offset += ascii_len

    # 2) UTF-8 unit symbol
    utf_len = struct.unpack_from("<i", data, offset)[0]
    offset += 4
    header["unit_symbol"] = data[offset : offset + utf_len].decode("utf-8", errors="replace")
    offset += utf_len

    # 3) Unit multiplier (float64)
    header["unit_multiplier"] = struct.unpack_from("<d", data, offset)[0]
    offset += 8

    # Walk flags exactly like your original code: 4 bytes at a time
    if body_points * byte_length:
        header["flags"] = []
        for loc in range(offset, h_len, 4):
            val = struct.unpack_from("<i", data, loc)[0]
            if val != body_points:
                header["flags"].append(val)
        header["x_points"] = body_points
        header["data"] = data[h_len:]
        return header

    try:
        header |= find_data_start(data, offset, byte_length)
        return header
    except ValueError:
        raise


def find_data_start(data: bytes, offset: int = 0, byte_length: int = 0) -> dict:
    """Parse header of 1D Vector data."""
    header = {}
    d_len = len(data)

    # 4) Flags (int32 list)
    header["flags"] = []

    b_vals = [8, 4] if byte_length == 0 else [byte_length]
    for loc in range(offset, d_len, 4):
        val = struct.unpack_from("<i", data, loc)[0]
        for b_len in b_vals:
            if d_len - loc - 4 - val * b_len < 8:
                header["byte_length"] = b_len
                header["x_points"] = val
                h_len = d_len - val * b_len
                header["data"] = data[h_len:]
                return header

        header["flags"].append(val)

    raise ValueError("Unable to parse 1D Vector header")


def parse_xml_data_array(node, source="", **kwargs) -> dict:
    """
    Parse a Data Array node (typeid 64, 69).
    Decodes the data based on its encoding and extracts numerical values.

    Parameters
    ----------
    node : dict
        The XML node representing the Data Array.
    source : str
        The source type (e.g., "Matrix", "Array").
    Returns
    -------
    dict
        A dictionary containing the decoded data and metadata.
    """

    encoding = node.get("encoding", "").lower()
    encoded = node.get("text", "").strip()

    if not encoded or not encoding:
        return node  # leave untouched

    data = {k: v for k, v in node.items() if k in ("encoding", "size", "typename")}

    try:
        data["size"] = eval(data["size"])
    except (NameError, SyntaxError, KeyError):
        pass

    # def/base64 → the only encoding you've actually seen
    if encoding == "def/base64":
        data["raw"] = base64.b64decode(encoded)
    # gzip/base64 → optional future-proofing
    elif encoding == "gzip/base64":
        data["raw"] = gzip.decompress(base64.b64decode(encoded))
    else:
        return {**node, **data}

    num_points, byte_length = parse_axis_info(len(data["raw"]), kwargs.get("info", {}), source)

    if source == "Matrix":
        header = parse_header_2d_matrix(data["raw"], num_points, byte_length)
    elif source == "Array":
        header = parse_header_1d_data(data["raw"], num_points, byte_length)
    else:
        header = parse_header_1d_vector(data["raw"], num_points, byte_length)

    # header, raw = decode_axis_bytes(data["raw"], byte_type, num_points, byte_length)
    byte_length = header.pop("byte_length", byte_length)
    dtype = np.float64 if byte_length == 8 else np.float32

    data |= header
    data["data"] = np.frombuffer(header["data"], dtype=dtype)

    if source == "Matrix":
        data["data"] = data["data"].reshape((header["x_points"], header["y_points"]))

    return data


def decode_xml_types(node: dict, info: dict | None = None, pkey: str = "") -> Any:
    """
    Recursively decode typed nodes in a DigitalSurf XML structure.

    Parameters
    ----------
    node : dict
        The XML node to decode.
    info : dict, optional
        A dictionary containing additional information for decoding.
    pkey : str, optional
        The parent key for context.
    Returns
    -------
    Any
        The decoded node value. Ultimately returns a dict in most cases.
    """
    # Base case: not a dict → nothing to do
    if info is None:
        info = {}

    if not isinstance(node, dict):
        return node

    data = node.copy()

    # If this node has a typeid, try to parse it
    typeid = node.get("typeid")
    parsed = None
    if typeid in CONTAINER_TYPES:
        parsed = parse_xml_container(node, info=info, source=pkey)
    elif typeid in DIRECT_TYPES:
        default = TYPEID_INFO_MAP[typeid][4] if typeid in TYPEID_INFO_MAP else ""
        parsed = parse_xml_string(node, info=info, source=pkey, _default=default)
        if typeid == 1:
            parsed = bool(parsed)
    elif typeid in VECTOR_TYPES:
        parsed = parse_xml_data_array(node, info=info, source=pkey)
    elif typeid == 14:
        parsed = parse_xml_named_data(node, info=info, source=pkey)
    elif typeid == 19:
        parsed = parse_xml_unit_value(node, info=info, source=pkey)
    elif typeid == 66:
        parsed = parse_xml_str_vector(node, info=info, source=pkey)
    elif typeid == 124:
        parsed = parse_xml_pos_function(node, info=info, source=pkey)
    # elif typeid in PARSERS:
    #     parsed = PARSERS[typeid](data, info=info, source=pkey)

    # If parser returns a scalar, stop recursion
    if parsed is not None:
        if not isinstance(parsed, dict):
            return parsed
        data = parsed

    # Recurse into merged fields
    result = {}
    for key, value in list(data.items()):
        result[key] = (
            decode_xml_types(value, info=info, pkey=key) if isinstance(value, dict) else value
        )

    return result


# %% --- Clean and restructure parsed XML ---


def get_attribute_from_raw_xml(source, *targets, sep=".") -> dict:
    """
    Flatten a parsed DigitalSurf XML dict into a flat dict mapping
    merged hierarchical keys → target attribute value.

    Parameters
    ----------
    tree : dict
        Parsed node from _parse_bruker_node().
    targets : str
        Attribute name to extract (e.g. "typeid", "encoding", "value").
    sep : str
        Separator used to join hierarchical keys.

    Returns
    -------
    flat : dict
        { "path.to.node" : attribute_value }
    """

    flat = defaultdict(dict)
    if not targets:
        return flat

    def walk(node, path):
        # If this node has the target attribute, record it
        key = path if path else sep
        for targ in targets:
            if targ in node:
                flat[key][targ] = node[targ]

        # Recurse into children if present
        children = node.get("children")
        if isinstance(children, dict):
            for key, child in children.items():
                child_path = f"{path}{sep}{key}" if path else key
                walk(child, child_path)

    # Root key may be None or missing; use empty path
    root_key = source.get("key", "")
    walk(source, root_key)

    flat = dict(flat)
    if len(targets) == 1:
        targ = targets[0]
        flat = {k: v[targ] for k, v in flat.items() if targ in v}

    return flat


def read_bruker_xml(path: Path | str, decode: bool = True, clean: bool = True) -> dict:
    """
    Read and parse a DigitalSurf XML file.

    Parameters
    ----------
    path : Path or str
        Path to the XML file.
    decode : bool, optional
        Whether to decode typed nodes. Default is True.
    clean : bool, optional
        Whether to clean and restructure the parsed XML. Default is True.
    Returns
    -------
    dict
        The parsed (and optionally decoded and cleaned) XML data.
    """
    path = Path(path)
    tree = ET.parse(path)
    root = tree.getroot()

    result, info = _parse_bruker_node(root)

    # --- Metadata ---
    result["filename"] = path.name
    result["path"] = str(path)
    result.setdefault("timestamp", oldest_timestamp(path))

    if decode:
        def_2d = "children" in result["children"]["2D_Data"]
        eval_file_info(info, format_name="bruker-xml", def_2d=def_2d)
        if "standard" in info["source_format"]:
            if "children" not in result["children"]["2D_Data"]:
                result["children"].pop("2D_Data", None)
            else:
                warnings.warn(
                    "Detected 2D_Data block in standard (1d) measurement. Check data integrity."
                )
        elif "map" in info["source_format"]:
            if "children" not in result["children"]["1D_Data"]:
                result["children"].pop("1D_Data", None)
            else:
                warnings.warn(
                    "Detected 1D_Data block in map (2d) measurement. Check data integrity."
                )

        result = decode_xml_types(result, info=info)
        if clean:

            result = clean_bruker(result)

    return result


# %% Tools


def build_attr_name_map(flat_dict, sep="."):
    """
    Convert a flat XML dict into:
        { typeid : {valid_ascii_names} }

    Rules:
      - Split each key on `sep`
      - First segment must be an integer (typeid)
      - Last segment is the ASCII name to allow
    """
    out = {}

    for key, val in flat_dict.items():
        parts = key.split(sep)
        if not parts or not parts[-1]:
            continue

        # typeid must be an integer
        try:
            tid = int(val)
        except ValueError:
            continue

        name = parts[-1]

        if tid not in out:
            out[tid] = set()

        out[tid].add(name)

    return out


def gen_attr_name_map_from_folder(
    folder: Path | str, attr: str = "typeid", sep: str = "."
) -> dict:
    """
    Generate a mapping of attr to valid ASCII names from all XML files in a folder.

    Parameters
    ----------
    folder : Path or str
        Path to the folder containing XML files.
    sep : str
        Separator used to join hierarchical keys.

    Returns
    -------
    dict
        A mapping of attr to sets of valid ASCII names.
    """
    folder = Path(folder)
    attr_name_map = {}

    for xml_file in folder.glob("*.xml"):
        xml_data = read_bruker_xml(xml_file, decode=False)
        flat_attrs = get_attribute_from_raw_xml(xml_data, attr, sep=sep)
        file_map = build_attr_name_map(flat_attrs, sep=sep)

        for tid, names in file_map.items():
            attr_name_map.setdefault(tid, set()).update(names)

    return {a: attr_name_map[a] for a in sorted(attr_name_map)}


# %% --- Example usage ---
if __name__ == "__main__":
    # Example usage
    gd_folder = Path(
        r"D:\\Online\ASU Dropbox\Jacob Clenney\Work Docs\Data\Analysis\Profilometry\GDOES"
    )

    xml_1d_raw = read_bruker_xml(gd_folder / "evap_prof_3.xml", decode=False)

    xml_2d_raw = read_bruker_xml(gd_folder / "n15s2_2.xml", decode=False)

    # "n15s2_2.xml" ; "evap_prof_3.xml"
    # xml_results = read_bruker_xml(gd_folder / "n15s2_2.xml")

    xml_1d_results = read_bruker_xml(gd_folder / "evap_prof_3.xml")

    xml_2d_results = read_bruker_xml(gd_folder / "n15s2_2.xml")

    # decoded = decode_xml_types(xml_results)

    # flt_dict = clean_bruker_xml(decoded)

    # type_ids = get_attribute_from_raw_xml(xml_results, "typeid")

    # texts = get_attribute_from_raw_xml(xml_results, "text")

    # strings = get_attribute_from_raw_xml(xml_results, "Str")

    # tags = get_attribute_from_raw_xml(xml_results, "tag")

    # encodes = get_attribute_from_raw_xml(xml_results, "encoding")

    # id_tags = {k: (v, tags[k]) for k, v in type_ids.items()}

    # un_val = get_attribute_from_raw_xml(xml_results, "Unit", "Value")

    # un_val = get_attribute_from_raw_xml(xml_results, "Unit", "Value")

    # un_val_id = {k: v | {"typeid": type_ids[k]} if k in type_ids else v for k, v in un_val.items()}

# def parse_axis_info(d_len: int, info: dict | None, source: str) -> tuple[int, int]:
#     """
#     Determine number of points and byte length per point for axis data.

#     Parameters
#     ----------
#     d_len : int
#         Total length of the data in bytes.
#     info : dict, optional
#         Additional information about the data.
#     source : str
#         Source type (e.g., "Matrix", "Array").

#     Returns
#     -------
#     tuple
#         A tuple containing the number of points and byte length per point.
#     """
#     byte_length = 0
#     num_points = 0
#     if info:
#         as_2d = info["is_2d"]
#         num_points = info["num_points"]
#         if num_points > 0:
#             byte_length = d_len / num_points
#             if byte_length not in (4, 8):
#                 if info["data_dtype"] == "float32":
#                     byte_length = 4
#                 elif info["data_dtype"] == "float64":
#                     byte_length = 8
#                 else:
#                     byte_length = 0
#     else:
#         as_2d = "matrix" in source.lower()
#         byte_length = 4 if as_2d else 8

#     if num_points and not byte_length:
#         byte_length = d_len // num_points
#         if byte_length not in (4, 8):
#             # Choose the most likely dtype based on smallest mismatch
#             delta_8 = d_len - num_points * 8
#             delta_4 = d_len - num_points * 4
#             if delta_8 < 0 and delta_4 < 0:
#                 raise ValueError("Not enough bytes for specified num_points")
#             byte_length = 8 if 0 <= delta_8 < delta_4 else 4

#     return num_points, byte_length


# def clean_bruker_xml(raw_dict: dict, fmt_name: str = "bruker-xml") -> dict:
#     """
#     Cleans and restructures a parsed DigitalSurf XML dictionary.

#     Parameters
#     ----------
#     raw_dict : dict
#         The parsed XML dictionary from decode_xml_types().
#     Returns
#     -------
#     dict
#         A cleaned and restructured dictionary.
#     """
#     flt_dict: dict[str, Any] = flatten_dict(raw_dict, sep=".")
#     flt_dict = {BRUKER_RENAME_MAP.get(k, k): v for k, v in flt_dict.items()}

#     # if "two_d_block" in flt_dict and flt_dict["two_d_block"] is None:
#     if "standard" in flt_dict["measurement"].lower():
#         flt_dict["source_format"] = f"{fmt_name}: standard (1d)"
#         flt_dict["z_array"] = flt_dict["data"] * flt_dict["z_scale"]

#     # elif "one_d_block" in flt_dict and flt_dict["one_d_block"] is None:
#     elif "map" in flt_dict["measurement"].lower():
#         flt_dict["source_format"] = f"{fmt_name}: map (2d)"
#         flt_dict["x_scale"] = flt_dict["x_max"] / flt_dict["x_points"]
#         flt_dict["y_scale"] = flt_dict["y_max"] / flt_dict["y_points"]
#         flt_dict["x_array"] = np.arange(0, flt_dict["x_points"]) * flt_dict["x_scale"]
#         flt_dict["y_array"] = np.arange(0, flt_dict["y_points"]) * flt_dict["y_scale"]
#         flt_dict["z_array"] = flt_dict["data"] * flt_dict["z_scale"]

#     # --- 2. Sub-groupings ---
#     # group data, x_items, y_items, z_items, and t_items
#     out = {}
#     out["data"] = {}
#     for key in ["z_array", "x_array", "y_array"]:
#         if key in flt_dict:
#             out["data"][key] = flt_dict.pop(key, None)

#     out["data_info"] = {}
#     for key in list(flt_dict.keys()):
#         if key.startswith(("z_", "x_", "y_")):
#             out["data_info"][key] = flt_dict.pop(key, None)

#     for k in PRIORITY_META:
#         if k in flt_dict:
#             out[k] = flt_dict.pop(k, None)

#     out["other_metadata"] = flt_dict.copy()


#     return out

# PARSERS = {
#     # 1: lambda v, **d: bool(parse_xml_string(v, _default=False, **d)),  # Boolean
#     # 6: lambda v, **d: parse_xml_string(v, _default=0, **d),  # Integer
#     # 7: lambda v, **d: parse_xml_string(v, _default=0, **d),  # Integer
#     # 11: lambda v, **d: parse_xml_string(v, _default=0, **d),  # double-integer
#     # 12: lambda v, **d: parse_xml_string(v, _default=0.0, **d),  # Single-precision float
#     # 13: lambda v, **d: parse_xml_string(v, _default=0.0, **d),  # Double-precision float
#     # 14: parse_xml_named_data,  # Named Data
#     # 18: parse_xml_string,  # String
#     # 19: parse_xml_unit_value,  # Unit-Value pair
#     # 21: parse_datetime,  # DateTime
#     # 64: parse_xml_data_array,  # 1d Data
#     # 66: parse_xml_str_vector,  # String Vector
#     # 69: parse_xml_data_array,  # 2D Data
#     # 70: parse_xml_container,  # Raw Container
#     # 71: parse_xml_container,  # Raw Container
#     # 124: parse_xml_pos_function,  # Contains info to make axis or axis data
#     # 125: parse_xml_container,  # Container
# }
