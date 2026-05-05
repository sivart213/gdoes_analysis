import re
import copy
import struct
from typing import Any, Literal, TypeVar, Callable, overload
from collections import defaultdict
from collections.abc import Collection

import numpy as np
import pandas as pd

from gdoes_analysis.gd_file_parsing.definitions import PART_TRANSLATIONS, DIRECT_TRANSLATIONS

T = TypeVar("T", bound=Collection)


@overload
def to_num(arr: pd.DataFrame) -> pd.DataFrame: ...
@overload
def to_num(arr: pd.Series) -> pd.Series: ...


def to_num(arr: pd.DataFrame | pd.Series) -> pd.DataFrame | pd.Series:
    # return arr.apply(to_num_col)
    if isinstance(arr, pd.DataFrame) and arr.shape[1] > 1:
        return arr.apply(to_num_col)
    return arr.apply(to_num_item)


def to_num_col(x):
    try:
        return pd.to_numeric(x)
    except Exception:
        return x.infer_objects()


def to_num_item(x):
    try:
        return pd.to_numeric(x)
    except Exception:
        return x.apply(to_num_item) if isinstance(x, pd.Series) else x


def recursive_apply(
    data: Any,
    recurse_type: type,
    func: Callable[[Any], Any],
) -> Any:
    if isinstance(data, recurse_type):
        res = [recursive_apply(d, recurse_type, func) for d in data]
        return recurse_type(res)
    else:
        return func(data)


@overload
def multi_partition(
    raw: bytes, *seps: bytes, decode: Literal[False]
) -> tuple[list[bytes], bytes]: ...
@overload
def multi_partition(
    raw: bytes, *seps: bytes, decode: Literal[True] = True
) -> tuple[list[str], bytes]: ...


def multi_partition(
    raw: bytes, *seps: bytes, decode: bool = True
) -> tuple[list[str] | list[bytes], bytes]:
    """
    Partition raw bytes sequentially by a list of separators.
    Returns a list of sections and the remainder. tuple[list[str], bytes] | tuple[list[bytes], bytes]
    """
    sections = []
    resid = raw
    for sep in seps:
        part, _, resid = resid.partition(sep)
        sections.append(part.decode("utf-8", errors="ignore") if decode else part)
    return sections, resid


@overload
def multi_split(
    section: str,
    *seps: str | list[str],
    decode: bool = ...,
    encoding: str = ...,
    errors: str = ...,
) -> list: ...


@overload
def multi_split(
    section: bytes,
    *seps: bytes | list[bytes],
    decode: bool = ...,
    encoding: str = ...,
    errors: str = ...,
) -> list: ...


def multi_split(
    section,
    *seps,
    decode=True,
    encoding="utf-8",
    errors="ignore",
):
    """
    Recursively split section by a list of separators.
    Each separator is applied in order, producing nested lists.
    Works on str or bytes directly.
    """
    if not seps or not section:
        return (
            [section.decode(encoding, errors=errors)]
            if isinstance(section, bytes) and decode
            else [section]
        )

    if isinstance(seps[0], list):
        for sub_sep in seps[0]:
            parts: Any = re.split(sub_sep, section, flags=re.S)
            if len(parts) > 1:
                break
        else:
            parts = [section]
    else:
        parts: Any = re.split(seps[0], section, flags=re.S)

    if len(seps) == 1:
        return (
            [p.decode(encoding, errors=errors) for p in parts]  # if p
            if decode and isinstance(section, bytes)
            else parts
        )
    return [
        multi_split(p, *seps[1:], decode=decode, encoding=encoding, errors=errors)
        for p in parts
        if p
    ]


def group_by_len(rows: list[T] | tuple[T, ...]) -> list[list[T]]:
    """Group rows by consistent length."""
    groups: list[list[T]] = []
    current_group: list[T] = []
    current_len = len(rows[0]) if rows else 0
    for row in rows:
        if len(row) == current_len:
            current_group.append(row)
        else:
            groups.append(current_group)
            current_group = [row]
            current_len = len(row)
    if current_group:
        groups.append(current_group)
    return groups


def _get_empty_positions(row, strict: bool) -> list[int]:
    """
    Return the indexes of empty elements in the row.
    If strict=True, only keep empties that form a prefix or suffix.
    Middle empties are removed entirely.
    """
    if strict:
        keep = set()

        # Prefix scan
        for i, v in enumerate(row):
            if v:
                break
            keep.add(i)
        else:
            return sorted(keep)

        # Suffix scan
        for i in range(len(row) - 1, -1, -1):
            if row[i]:
                break
            keep.add(i)

        return sorted(keep)  # Strict removes middle empties entirely
    return [i for i, v in enumerate(row) if not v]


def expand_headers(headers: list, prefix) -> list:
    """
    Expand headers of the form:
        <prefix><digits><name>
    into:
        name1, name2, ..., nameN

    If no digits follow the prefix, count defaults to 1.
    """
    if not headers or not prefix:
        return headers

    if isinstance(headers[0], (list, tuple)):
        return [expand_headers(h, prefix) for h in headers]

    out = []
    # Regex: prefix, optional digits, then the rest of the name
    pattern = re.compile(rf"(.*){re.escape(prefix)}(\d*)(.*)")

    for h in headers:
        m = pattern.fullmatch(h)
        if not m:
            # No prefix at all → treat entire header as name with count=1
            out.append(h)
            continue

        before, digits, after = m.groups()

        name = f"{before}{after}"

        if not digits or digits == "1":
            out.append(name)
            continue

        out.extend(f"{name}_{i}" for i in range(int(digits)))

    return out


def check_single_groups(
    groups: list[list[list[T]]],
    strict: bool = True,
    fwd: bool = True,
    rev: bool = True,
    prefix: str = "",
) -> list[list[list[T]]]:
    """
    Attempt to merge groups where one group has extra empty columns that can be
    removed to match the length of a neighbor group.

    groups: output of group_by_len
    strict: empties must be at start/end (True) or anywhere (False)
    fwd: allow merging into next group
    rev: allow merging into previous group
    """
    if not groups:
        return groups

    groups = copy.deepcopy(groups)

    m_groups: list[list[list[T]]] = []
    glen = len(groups)
    n = 0
    while n < glen:
        single = groups[n]
        # Skip empty and multi-list groups
        if len(single) != 1:
            if single:
                m_groups.append(single)
            n += 1
            continue

        # Single-list group: candidate for merge
        row = single[0]
        row_len = len(row)
        row_expanded = False
        if prefix:
            row = expand_headers(row, prefix)
            if len(row) != row_len:
                row_expanded = True
                row_len = len(row)

        # Determine empty positions using your updated logic
        empty_idxs = _get_empty_positions(row, strict=strict)

        # If no empties, cannot merge
        if not empty_idxs and not row_expanded:
            m_groups.append(single)
            n += 1
            continue

        # Forward merge
        if fwd and n + 1 < glen and groups[n + 1]:
            next_group = groups[n + 1]
            if row_expanded and len(next_group[0]) == row_len:
                # Expanded row matches next group length
                m_groups.append([row] + next_group)
                n += 2
                continue
            if 0 < (n_rem := row_len - len(next_group[0])) <= len(empty_idxs):
                # Merge into next group
                idxs = set(empty_idxs[:n_rem]) if empty_idxs[0] == 0 else set(empty_idxs[-n_rem:])
                m_groups.append([[v for i, v in enumerate(row) if i not in idxs]] + next_group)
                n += 2
                continue

        # Reverse merge
        if rev and m_groups:
            prev_group = m_groups[-1]
            if row_expanded and len(prev_group[0]) == row_len:
                # Expanded row matches previous group length
                m_groups[-1] = prev_group + [row]
                n += 1
                continue
            if 0 < (n_rem := row_len - len(prev_group[0])) <= len(empty_idxs):
                # Merge into previous group
                idxs = set(empty_idxs[:n_rem]) if empty_idxs[0] == 0 else set(empty_idxs[-n_rem:])
                m_groups[-1] = prev_group + [[v for i, v in enumerate(row) if i not in idxs]]
                n += 1
                continue

        m_groups.append(single)
        n += 1

    return m_groups


def make_dataframe(cols: list[Any], *data: list[Any]) -> pd.DataFrame:
    """Convert a group of rows into a DataFrame."""
    return pd.DataFrame(data, columns=cols)


def rename_columns(df):
    """
    Rename DataFrame columns using:
      1. direct_map for exact matches
      2. part_map for substring replacements
      3. fallback to original name

    Returns a new DataFrame with renamed columns.
    """
    new_cols = {}

    for col in df.columns:
        # 1. Direct translation
        if col in DIRECT_TRANSLATIONS:
            new_cols[col] = DIRECT_TRANSLATIONS[col]
            continue
        if col[-1].isdigit():
            base_col = re.sub(r"_\d+$", "", col)
            if base_col in DIRECT_TRANSLATIONS:
                new_cols[col] = f"{DIRECT_TRANSLATIONS[base_col]}_{col.split('_')[-1]}"
                continue

        # 2. Part translations using two working strings
        remove_working = col  # parts removed here
        new_name = col
        for part in sorted(PART_TRANSLATIONS.keys(), key=len, reverse=True):
            repl = PART_TRANSLATIONS[part]
            if part in remove_working:
                remove_working = remove_working.replace(part, "", 1)
                new_name = new_name.replace(part, repl, 1)
            if not remove_working:
                break

        # 3. Fallback: keep original
        new_cols[col] = new_name

    return df.rename(columns=new_cols)


def parse_section_id(raw_id: bytes) -> tuple[bytes, str]:
    """
    Iterate down from min(8, n) to 1.
    At each candidate length L, check if raw_id[-(L+1)] == L.
    If so, split: info = raw_id[:-(L+1)], name = raw_id[-L:].
    """
    n = len(raw_id)
    for L in range(min(8, n), 0, -1):  # iterate downwards
        pos = n - (L + 1)
        if pos < 0:
            continue
        if raw_id[pos] == L:
            info = raw_id[:pos]
            name_bytes = raw_id[-L:]
            try:
                name = name_bytes.decode("utf-8")
            except UnicodeDecodeError:
                name = name_bytes.decode("utf-8", errors="ignore")
            return info, name
    # fallback: no marker found
    return b"", ""


def parse_body(raw: list[bytes] | bytes, sep: bytes = b""):
    """
    Parse the body of the raw data into sections.
    """
    if isinstance(raw, list):
        chunks: list[bytes] = raw
    else:
        if not sep:
            raise ValueError("Separator must be provided when raw is bytes.")
        chunks = raw.split(sep)  # type: ignore

    # --- parse body ---
    sections: dict[str, list[tuple[float, float]]] = defaultdict(list)
    infos: dict[str, bytes] = {}
    section_id = "unknown"

    for chunk in chunks:
        if len(chunk) > 8:
            # header/footer overlap
            raw_id = chunk
            if sections.get(section_id, []):
                sections[section_id].append(struct.unpack("<ff", chunk[:8]))
                raw_id = chunk[8:]
            info, section_id = parse_section_id(raw_id)
            infos[section_id] = info
        elif len(chunk) == 8:
            # pure data record
            sections[section_id].append(struct.unpack("<ff", chunk))

    sections = dict(sections)

    # --- post-process infos ---
    if infos:
        lengths = [len(v) for v in infos.values()]
        med_len = int(np.median(lengths))

        extras: dict[str, bytes] = {}
        for length, (sid, info) in zip(lengths, infos.items()):
            if length > med_len:
                # prefix is everything before that
                extras[f"{sid}_prefix"] = info[:-med_len]
                # keep the *last* med_len bytes as infos[sid]
                infos[sid] = info[-med_len:]

        if extras:
            if len(extras) == 1:
                # only one item with extra → data_prefix
                infos["data_prefix"] = next(iter(extras.values()))
            else:
                # multiple extras → merge directly
                infos |= extras

    return sections, infos


def create_body_dfs_alt2(
    sections: dict[str, list[tuple[float, float]]],
    infos: dict[str, bytes],
) -> tuple[list[pd.DataFrame], pd.DataFrame]:
    """
    Create DataFrames from parsed sections.

    - Sections with identical X arrays are grouped into the same DataFrame.
    - A raw DataFrame is also created with all sections padded with NaNs.
    - Returns (list_of_grouped_dfs, raw_df).
    """
    grouped: list[pd.DataFrame] = []
    shared_len = max(len(sec) for sec in sections.values())

    raw_cols = {}

    for section_id, sec in sections.items():
        xs, ys = list(zip(*sec))

        # populate raw_df
        pad = [np.nan] * (shared_len - len(sec))
        raw_cols[f"{section_id}_X"] = list(xs) + pad
        raw_cols[section_id] = list(ys) + pad

        # try to place into an existing group
        for gdf in grouped:
            if len(xs) == len(gdf) and np.allclose(xs, gdf["X"], rtol=1e-6, atol=1e-8):
                gdf[section_id] = ys
                if section_id in infos:
                    gdf.attrs["prefixes"][section_id] = infos[section_id]
                break
        else:
            # no match → create new group
            grouped.append(pd.DataFrame({"X": xs, section_id: ys}))
            grouped[-1].attrs["prefixes"] = {}
            if section_id in infos:
                grouped[-1].attrs["prefixes"][section_id] = infos[section_id]

    raw_df = pd.DataFrame(raw_cols)
    raw_df.attrs["info"] = infos

    for df in grouped:
        df.attrs["other_info"] = {k: v for k, v in infos.items() if k not in df.attrs["prefixes"]}
    return grouped, raw_df


def create_body_dfs(
    sections: dict[str, list[tuple[float, float]]],
    infos: dict[str, bytes],
) -> tuple[pd.DataFrame, pd.DataFrame]:

    shared_len = max(len(sec) for sec in sections.values())

    # -----------------------------
    # 1. Build raw_df exactly as before
    # -----------------------------
    raw_cols = {}
    for section_id, sec in sections.items():
        xs, ys = list(zip(*sec))
        pad = [np.nan] * (shared_len - len(sec))
        raw_cols[f"{section_id}_X"] = list(xs) + pad
        raw_cols[section_id] = list(ys) + pad

    raw_df = pd.DataFrame(raw_cols)
    raw_df.attrs["info"] = infos

    # -----------------------------
    # 2. Build merged_df by deduplicating X columns
    # -----------------------------
    merged_df = raw_df.copy()
    arr = merged_df.to_numpy()

    # Find unique X columns using minimal variables
    avail = set(range(0, arr.shape[1], 2))
    dupl_map = {}
    while avail:
        idx = min(avail)
        avail.remove(idx)
        dup = {x for x in avail if np.array_equal(arr[:, x], arr[:, idx])}
        dupl_map[idx] = dup
        avail -= dup

    # -----------------------------
    # 3. Single-unique-X fast path
    # -----------------------------
    if len(dupl_map) == 1:
        merged_df = merged_df.iloc[:, list(dupl_map.keys()) + list(range(1, arr.shape[1], 2))]
        merged_df = merged_df.rename(columns={merged_df.columns[0]: "X"})
        merged_df.attrs |= raw_df.attrs
        return merged_df, raw_df

    print(f"Detected {len(dupl_map)} unique X columns across {len(sections)} sections.")
    # -----------------------------
    # 4. Multi-X case (fully driven by dupl_map)
    # -----------------------------
    cols: list[int] = []
    name_map: dict[str, str] = {}

    # iterate primaries in sorted order to preserve left-to-right structure
    for i, (x_idx, x_set) in enumerate(dupl_map.items(), start=1):
        # x_idx X and its own Y
        cols.append(x_idx)
        cols.append(x_idx + 1)
        cols.extend(sorted(dup + 1 for dup in x_set))
        name_map[merged_df.columns[x_idx]] = f"X{i}"

    merged_df = merged_df.iloc[:, cols]
    merged_df = merged_df.rename(columns=name_map)
    merged_df.attrs |= raw_df.attrs
    return merged_df, raw_df


def test_unpack_format(df: pd.DataFrame, fmt: str, source_col: str = "raw_bytes") -> pd.DataFrame:
    """
    Apply a struct format to the raw_bytes column of a parsed .fic DataFrame.

    Parameters
    ----------
    df : pd.DataFrame
        The DataFrame returned by parse_fic_table (must contain 'raw_bytes').
    fmt : str
        A struct format string (e.g., '<i20sH').

    Returns
    -------
    pd.DataFrame
        A copy of df with:
        - new columns for each unpacked field
        - a 'remaining_bytes' column containing any leftover bytes
    """

    st = struct.Struct(fmt)
    # Copy so we never mutate the original
    out = df.copy()

    if "remaining_bytes" in out.columns:
        out = out.drop(columns=["remaining_bytes"])

    data = []

    # Convert repr(raw_bytes) → bytes once, then iterate
    for idx, raw in df[source_col].apply(eval).items():
        if len(raw) < st.size:
            raise ValueError(
                f"Row {idx}: raw_bytes too short for format " f"(got {len(raw)}, need {st.size})"
            )

        # Unpack the first st.size bytes
        fields = [
            x.decode(errors="ignore").strip() if isinstance(x, (bytes, bytearray)) else x
            for x in list(st.unpack_from(raw, 0))
        ]
        fields.append(repr(raw[st.size :]))
        data.append(fields)

    # Build column names: f0, f1, f2, ...
    unpacked_cols = [
        f"col_{i}" for i in range(len(out.columns), len(out.columns) + len(data[0]) - 1)
    ] + ["remaining_bytes"]

    # Add unpacked fields to the output DataFrame
    unpacked_df = pd.DataFrame(data, columns=unpacked_cols, index=df.index)
    for col in unpacked_cols:
        out[col] = unpacked_df[col]

    return out


def _find_pre_header(data: bytes):
    """
    Try pre_header_len from 4 to 16 (inclusive).
    Return:
      pre_header, row_count, data_count
    """
    n = len(data)
    if n < 64:
        raise ValueError("Data too short to parse .blk measurement.")

    row_opts: list[tuple[bytes, int, int]] = [
        (data[:i],) + struct.unpack_from("<2i", data, i) for i in list(range(4, 17))
    ]
    if 35 < row_opts[1][1] <= 50 and 2 <= row_opts[1][2] <= 15 and row_opts[1][0] == b"\x04#@%!":
        # Favor pre_header_len=5 if it looks good
        return row_opts[1]

    sub_row_opts = [(hd, rc, dc) for hd, rc, dc in row_opts if 0 < rc <= 128]

    if not sub_row_opts:
        raise ValueError("No valid pre-header length found with plausible row count.")

    for row_opt in sub_row_opts:
        pre_header, row_count, data_count = row_opt

        # 8 bytes prefix + 4 bytes se + 2 floats (4 bytes each)
        pred_bod_len = row_count * (8 + data_count * (4 + 2 * 4))
        pred_phead_len = len(pre_header) + 8
        pred_head_len = pred_phead_len + row_count * 8
        pred_len = pred_head_len + pred_bod_len
        if pred_len == n:
            return pre_header, row_count, data_count
        first = struct.unpack_from("<2i", data, pred_phead_len)
        if first[1] == pred_bod_len:
            return pre_header, row_count, data_count

    raise ValueError("No valid pre-header length found matching data size.")


def parse_blk_meas(data: bytes) -> tuple[pd.DataFrame, pd.DataFrame]:
    """
    Parse a .blk measurement data stream into:
      pre_header: raw bytes
      df: numeric data (Elem_idx, Intens_i, Std_i)
      df_info: metadata (Elem_idx, Row_Start_loc, Row_Prefix, Sep_i)
    """
    # --- 1. Determine pre_header_len and basic row_info --------------------
    pre_header, row_count, data_count = _find_pre_header(data)

    skip = len(pre_header) + 8

    row_info = [struct.unpack_from("<2i", data, i) for i in range(skip, skip + row_count * 8, 8)]

    row_ids, row_starts = zip(*row_info)

    if any(rs < 0 or rs >= len(data) for rs in row_starts):
        raise ValueError("One or more row start offsets are outside data bounds.")
    if any(rid < 1 or rid > 128 for rid in row_ids):
        raise ValueError("One or more row ids are outside valid range [1, 128].")

    # --- 4. Build row struct and parse rows --------------------------------
    # structure is 8-byte index, then (4-byte separator + 2 floats) * data_count
    # i.e. 8s + data_count * (4s, float32, float32)
    row_struct = struct.Struct("<2f" + ("i2f" * data_count))

    val_rows = []
    info_rows = []
    attrs = {0: pre_header}
    for row_id, row_start in row_info:
        attrs[row_id] = data[row_start : row_start + row_struct.size]
        try:
            row = row_struct.unpack_from(data, row_start)
        except struct.error as exc:
            raise ValueError(f"Failed to unpack row id {row_id} at offset {row_start}: {exc}")

        # slices: for each i, (sep_i, intens_i, std_i)
        codes, vals = list(
            zip(*[[row[i], (row[i + 1], row[i + 2])] for i in range(2, len(row), 3)])
        )
        val_arr = np.array(vals, dtype=float)

        avg_intens = float(val_arr[:, 0].mean())
        std_intens = float(val_arr[:, 0].std())

        val_rows.append([row_id, avg_intens, std_intens] + val_arr.flatten().tolist())
        info_rows.append([row_id, row_start, row[0], row[1]] + list(codes))

    # --- 5. Build DataFrames -----------------------------------------------
    df = pd.DataFrame(val_rows)
    df_info = pd.DataFrame(info_rows)

    # Construct column names programmatically
    df_cols = ["Elem_Line_Key", "intens_avg", "std_avg"]
    df_info_cols = ["Elem_Line_Key", "row_start_loc", "bkg", "bkg_std"]
    for i in range(1, data_count + 1):
        df_cols += [f"intens_{i}", f"std_{i}"]
        df_info_cols.append(f"code_{i}")

    df.columns = df_cols
    df_info.columns = df_info_cols

    df.attrs |= attrs.copy()
    df_info.attrs |= attrs.copy()

    return df, df_info


def make_elem_map(source) -> pd.Series:
    """
    Create an element-line mapping Series from:
      - a path
      - a dict of DataFrames
      - a DataFrame

    The returned Series is indexed by Elem_Line_Key and contains
    strings like "Fe 259" or "Cu 324".
    """
    # --- Case 1: path ------------------------------------------------------
    if isinstance(source, dict):
        # Try canonical keys
        for key in ("el", "elem_line", "Element"):
            if key in source:
                df = source[key]
                break
        else:
            # Fallback: search for df with required columns
            df = None
            for candidate in source.values():
                if {"Elem_Name", "Spectr_Line", "Elem_Line_Key"}.issubset(candidate.columns):
                    df = candidate
                    break

        if df is None:
            raise ValueError(
                "No valid element-line DataFrame found in dict. "
                "Expected key 'el', 'elem_line', 'Element', or a df containing "
                "Elem_Name, Spectr_Line, Elem_Line_Key."
            )

    # --- Case 3: DataFrame -------------------------------------------------
    elif isinstance(source, pd.DataFrame):
        df = source

    else:
        raise TypeError("source must be a path, dict of DataFrames, or a DataFrame.")

    # --- Validate required columns -----------------------------------------
    required = {"Elem_Name", "Spectr_Line", "Elem_Line_Key"}
    if not required.issubset(df.columns):
        raise ValueError(f"DataFrame missing required columns: {required - set(df.columns)}")

    # --- Build elem_map -----------------------------------------------------
    elem_map = df["Elem_Name"].astype(str) + " "
    elem_map += df["Spectr_Line"].apply(lambda x: str(int(round(x))) if x else "")
    elem_map.index = df["Elem_Line_Key"]

    return elem_map
