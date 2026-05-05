import struct
from pathlib import Path

import numpy as np
import pandas as pd


def _find_blk_header(data: bytes):
    """
    Try pre_header_len from 4 to 16 (inclusive).
    Return:
        pre_header, row_count, data_count, row_info
    """
    n = len(data)
    if n < 64:
        raise ValueError("Data too short to parse .blk measurement.")

    # Try all possible pre_header lengths
    row_opts: list[tuple[bytes, int, int]] = [
        (data[:i],) + struct.unpack_from("<2i", data, i) for i in list(range(4, 17))
    ]
    res = {}
    res["pre_header"], res["row_count"], res["data_count"] = row_opts[1]

    # Prefer pre_header_len = 5 if plausible
    if row_opts[1][0] == b"\x04#@%!" and 35 < row_opts[1][1] <= 50 and 2 <= row_opts[1][2] <= 15:
        try:
            res["row_info"] = _extract_blk_row_info(
                data, res["pre_header"], res["row_count"], res["data_count"]
            )
            return res
        except Exception:
            pass
    print(
        f"Debug: Trying to find .blk header, starting with pre_header_len={len(res['pre_header'])}"
    )
    # Otherwise test all candidates
    for pre_header, row_count, data_count in row_opts:
        if not (1 <= row_count <= 128):
            continue

        try:
            res["row_info"] = _extract_blk_row_info(data, pre_header, row_count, data_count)
        except Exception:
            continue
        res["pre_header"] = pre_header
        res["row_count"] = row_count
        res["data_count"] = data_count

        return res

    raise ValueError("No valid .blk pre-header found.")


def _extract_blk_row_info(data: bytes, pre_header: bytes, row_count: int, data_count: int):
    skip = len(pre_header) + 8
    n = len(data)

    # Extract row_info pairs
    row_info = [struct.unpack_from("<2i", data, i) for i in range(skip, skip + row_count * 8, 8)]

    # Validate row_starts
    row_ids, row_starts = zip(*row_info)
    # row_starts = [rs for _, rs in row_info]
    if any(rs < 0 or rs >= n for rs in row_starts):
        raise ValueError("Row start out of bounds.")
    if any(rid < 1 or rid > 128 for rid in row_ids):
        raise ValueError("One or more row ids are outside valid range [1, 128].")

    row_size = 8 + data_count * 12
    row_ends = list(row_starts[1:]) + [n]
    row_info = [info + (data[info[1] : row_ends[i]],) for i, info in enumerate(row_info)]

    if any(len(rc) != row_size for _, _, rc in row_info):
        raise ValueError("Inconsistent row lengths detected.")

    return row_info


def parse_blk_meas(data: bytes) -> tuple[pd.DataFrame, pd.DataFrame]:
    """
    Parse a .blk measurement data stream into:
      pre_header: raw bytes
      df: numeric data (Elem_idx, Intens_i, Std_i)
      df_info: metadata (Elem_idx, Row_Start_loc, Row_Prefix, Sep_i)
    """
    # --- 1. Determine pre_header_len and basic row_info --------------------
    # pre_header, row_count, data_count, row_info = _find_blk_header(data)
    info = _find_blk_header(data)

    row_struct = struct.Struct("<2f" + ("i2f" * info["data_count"]))

    val_rows = []
    info_rows = []
    attrs = {0: info["pre_header"]}
    for row_id, row_start, chunk in info["row_info"]:
        attrs[row_id] = chunk
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
    for i in range(1, info["data_count"] + 1):
        df_cols += [f"intens_{i}", f"std_{i}"]
        df_info_cols.append(f"code_{i}")

    df.columns = df_cols
    df_info.columns = df_info_cols

    df.attrs |= attrs.copy()
    df_info.attrs |= attrs.copy()

    return df, df_info


def load_blk_file(
    path: Path, elem_map: pd.Series | None = None, include_info: bool = False
) -> pd.DataFrame:
    """
    Load and parse a .blk measurement file into a DataFrame.
    """
    data = path.read_bytes()

    df0, df_info = parse_blk_meas(data)

    # Map element names
    dfs = []
    if elem_map is not None:
        names = elem_map[df0["Elem_Line_Key"]].reset_index(drop=True)
        dfs = [names, df0.iloc[:, 1:]]
        if include_info:
            dfs.append(df_info)
    else:
        dfs = [df0, df_info.iloc[:, 1:]] if include_info else []

    df = pd.concat(dfs, axis=1) if dfs else df0

    return df

    # Validate uniform row lengths
    # row_size = 8 + data_count * 12

    # row_ends = list(row_starts[1:]) + [n]

    # row_len = [row_starts[i] - row_starts[i - 1] for i in range(1, len(row_info))] + [
    #     n - row_starts[-1]
    # ]


# def _find_blk_pre_header(data: bytes):
#     """
#     Try pre_header_len from 4 to 16 (inclusive).
#     Return:
#       pre_header, row_count, data_count
#     """
#     n = len(data)
#     if n < 64:
#         raise ValueError("Data too short to parse .blk measurement.")

#     row_opts: list[tuple[bytes, int, int]] = [
#         (data[:i],) + struct.unpack_from("<2i", data, i) for i in list(range(4, 17))
#     ]
#     if 35 < row_opts[1][1] <= 50 and 2 <= row_opts[1][2] <= 15 and row_opts[1][0] == b"\x04#@%!":
#         # Favor pre_header_len=5 if it looks good
#         return row_opts[1]

#     sub_row_opts = [(hd, rc, dc) for hd, rc, dc in row_opts if 0 < rc <= 128]

#     if not sub_row_opts:
#         raise ValueError("No valid pre-header length found with plausible row count.")

#     for row_opt in sub_row_opts:
#         pre_header, row_count, data_count = row_opt

#         # 8 bytes prefix + 4 bytes se + 2 floats (4 bytes each)
#         pred_bod_len = row_count * (8 + data_count * (4 + 2 * 4))
#         pred_phead_len = len(pre_header) + 8
#         pred_head_len = pred_phead_len + row_count * 8
#         pred_len = pred_head_len + pred_bod_len
#         if pred_len == n:
#             return pre_header, row_count, data_count
#         first = struct.unpack_from("<2i", data, pred_phead_len)
#         if first[1] == pred_head_len:
#             return pre_header, row_count, data_count

#     raise ValueError("No valid pre-header length found matching data size.")
# skip = len(pre_header) + 8

# row_info = [struct.unpack_from("<2i", data, i) for i in range(skip, skip + row_count * 8, 8)]

# row_ids, row_starts = zip(*row_info)

# if any(rs < 0 or rs >= len(data) for rs in row_starts):
#     raise ValueError("One or more row start offsets are outside data bounds.")
# if any(rid < 1 or rid > 128 for rid in row_ids):
#     raise ValueError("One or more row ids are outside valid range [1, 128].")

# --- 4. Build row struct and parse rows --------------------------------
# structure is 8-byte index, then (4-byte separator + 2 floats) * data_count
# i.e. 8s + data_count * (4s, float32, float32)
