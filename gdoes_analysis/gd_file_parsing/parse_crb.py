import struct
from pathlib import Path

import pandas as pd

from gdoes_analysis.gd_file_parsing.parse_tools import create_body_dfs


def _find_crb_header(data: bytes):
    """
    Try pre_header_len from 4 to 16 (inclusive).
    Return:
        pre_header, row_count, data_count, row_info
    """
    n = len(data)
    if n < 64:
        raise ValueError("Data too short to parse .crb measurement.")

    # Try all possible pre_header lengths
    row_opts: list[tuple[bytes, int]] = [
        (data[:i], struct.unpack_from("<i", data, i)[0]) for i in range(4, 17)
    ]

    res = {}
    res["pre_header"], res["row_count"] = row_opts[1]
    # Prefer pre_header_len = 5 if plausible
    if res["pre_header"] == b"\x04#@&$" and 30 < res["row_count"] <= 50:
        try:
            res["row_info"] = _extract_crb_row_info(
                data, len(res["pre_header"]) + 4, res["row_count"]
            )
            return res
        except Exception:
            pass
    print(
        f"Debug: Trying to find .crb header, starting with pre_header_len={len(res['pre_header'])}"
    )
    # Otherwise test all candidates
    for pre_header, row_count in row_opts:
        if not (1 <= row_count <= 128):
            continue

        try:
            res["row_info"] = _extract_crb_row_info(data, len(pre_header) + 4, row_count)
        except Exception:
            continue
        res["pre_header"] = pre_header
        res["row_count"] = row_count
        return res

    raise ValueError("No valid .crb pre-header found.")


def _extract_crb_row_info(data: bytes, start: int, row_count: int):
    n = len(data)

    # Extract row_info pairs
    row_info = [struct.unpack_from("<2i", data, i) for i in range(start, start + row_count * 8, 8)]

    _, row_starts = zip(*row_info)

    # Validate row_starts
    if any(rs < 0 or rs >= n for rs in row_starts):
        raise ValueError("Row start out of bounds.")
    # if any(rid < 1 or rid > 128 for rid in row_ids):
    #     raise ValueError("One or more row ids are outside valid range [1, 128].")

    row_ends = list(row_starts[1:]) + [n]
    # row_info = [info + (data[info[1] : row_ends[i]],) for i, info in enumerate(row_info)]

    # row_len = []
    data_len = []
    for i, (rs, re) in enumerate(zip(row_starts, row_ends)):
        # row_len.append(re - rs)
        row_info[i] = row_info[i] + (data[rs:re],)
        data_len.append(re - (rs + 10 + data[rs + 9]))

    if data_len[0] % 12 != 0:
        raise ValueError("Row body not divisible into <i f f> triples.")
    if not all(dlen == data_len[0] for dlen in data_len):
        raise ValueError("Inconsistent data lengths detected.")

    return row_info


def parse_crb_meas(data: bytes) -> tuple[pd.DataFrame, pd.DataFrame]:
    """
    Parse a .blk measurement data stream into:
      pre_header: raw bytes
      df: numeric data (Elem_idx, Intens_i, Std_i)
      df_info: metadata (Elem_idx, Row_Start_loc, Row_Prefix, Sep_i)
    """
    # --- 1. Determine pre_header_len and basic row_info --------------------
    # pre_header, row_count = _find_crb_pre_header(data)
    info = _find_crb_header(data)

    row_struct = struct.Struct("<3B 6s b")

    val_rows = {}
    info_rows = {}
    info_rows["pre_header"] = info["pre_header"]
    info_rows["row_count"] = info["row_count"]
    for row_id, row_start, chunk in info["row_info"]:
        try:
            row_info = row_struct.unpack_from(data, row_start)
        except struct.error as exc:
            raise ValueError(f"Failed to unpack row id {row_id} at offset {row_start}: {exc}")

        head_len = row_struct.size + row_info[4]
        name = chunk[row_struct.size : head_len].decode("utf-8", errors="ignore")

        count = (len(chunk) - (head_len)) // 12
        try:
            row = struct.unpack_from("<" + count * "i2f", chunk, head_len)
        except struct.error as exc:
            raise ValueError(f"Failed to unpack row id {row_id} at offset {row_start}: {exc}")
        # slices: for each i, (sep_i, intens_i, std_i)
        codes, val_rows[name] = list(
            zip(*[[row[i], (row[i + 1], row[i + 2])] for i in range(0, len(row), 3)])
        )
        info_rows[name] = {}
        info_rows[name]["Row_ID"] = row_id
        info_rows[name]["Row_Start_loc"] = row_start
        info_rows[name]["color"] = (row_info[0], row_info[1], row_info[2])
        info_rows[name]["unparsed"] = row_info[3]
        info_rows[name]["name_len"] = row_info[4]
        info_rows[name]["codes"] = list(codes)
        info_rows[name]["raw"] = chunk

    # --- 5. Build DataFrames -----------------------------------------------
    df, df_info = create_body_dfs(val_rows, info_rows)

    return df, df_info


def load_crb_file(path: Path) -> pd.DataFrame:
    """
    Load and parse a .crb GDOES body file.
    """
    data = path.read_bytes()

    test1, test2 = parse_crb_meas(data)
    return test1

    # sections, infos = parse_body(data, sep=b"\x01\x00\x00\x00")
    # dfs, raw_df = create_body_dfs(sections, infos)

    # # Convention: dfs[0] is the main measurement table
    # return dfs[0]

    # row_len = [row_starts[i] - row_starts[i - 1] for i in range(1, len(row_info))] + [
    #     n - row_starts[-1]
    # ]

    # # Infer data_count from first row
    # first_start = row_starts[0]
    # ascii_len = data[first_start + 9]
    # ascii_block = 10 + ascii_len

    # remaining = n - (first_start + ascii_block)
    # if remaining % 12 != 0:
    #     raise ValueError("Row body not divisible into <i f f> triples.")

    # data_count = remaining // 12

    # # Validate uniform row lengths
    # # For each row:
    # #   ascii_len = data[row_start + 16]
    # #   ascii_block = 17 + ascii_len
    # #   row_size = ascii_block + data_count * 12
    # row_len = []
    # for rs in row_starts:
    #     a_len = data[rs + 9]
    #     a_block = 10 + a_len
    #     r_size = a_block + data_count * 12
    #     row_len.append(r_size)

    # # Check that the actual slice lengths match expected row_size
    # actual_len = [
    #     row_starts[i] - row_starts[i - 1] for i in range(1, len(row_starts))
    # ] + [n - row_starts[-1]]

    # if any(al != el for al, el in zip(actual_len, row_len)):
    #     raise ValueError("Inconsistent row lengths detected.")


# def _find_crb_pre_header(data: bytes):
#     """
#     Try pre_header_len from 4 to 16 (inclusive).
#     Return:
#       pre_header, row_count, data_count
#     """
#     n = len(data)
#     if n < 64:
#         raise ValueError("Data too short to parse .blk measurement.")

#     row_opts: list[tuple[bytes, int]] = [
#         (data[:i],) + struct.unpack_from("<i", data, i) for i in list(range(4, 17))
#     ]
#     if 30 < row_opts[1][1] <= 50 and row_opts[1][0] == b"\x04#@&$":
#         # Favor pre_header_len=5 if it looks good
#         return row_opts[1]

#     sub_row_opts = [(hd, rc) for hd, rc in row_opts if 0 < rc <= 128]

#     if not sub_row_opts:
#         raise ValueError("No valid pre-header length found with plausible row count.")

#     for row_opt in sub_row_opts:
#         pre_header, row_count = row_opt
#         pred_phead_len = len(pre_header) + 4
#         pred_head_len = pred_phead_len + row_count * 8
#         first = struct.unpack_from("<2i", data, pred_phead_len)
#         if first[1] == pred_head_len:
#             return pre_header, row_count

#     raise ValueError("No valid pre-header length found matching data size.")


# skip = len(pre_header) + 4

# row_info = [struct.unpack_from("<2i", data, i) for i in range(skip, skip + row_count * 8, 8)]

# row_ids, row_starts = zip(*row_info)

# if any(rs < 0 or rs >= len(data) for rs in row_starts):
#     raise ValueError("One or more row start offsets are outside data bounds.")
# if any(rid < 1 or rid > 128 for rid in row_ids):
#     raise ValueError("One or more row ids are outside valid range [1, 128].")

# row_chunks = [data[row_starts[i - 1] : row_starts[i]] for i in range(1, len(row_info))] + [
#     data[row_info[-1][1] :]
# ]

# val_rows = []
# info_rows = []
