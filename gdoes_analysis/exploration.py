import re
import struct
from pathlib import Path
from collections import Counter

import numpy as np
import pandas as pd
import chardet


def count_sequences(data: bytes, length: int) -> Counter[bytes]:
    """
    Count all subsequences of size `length` in the data.

    Parameters
    ----------
    data : bytes
        The raw byte string to scan.
    length : int
        The length (in bytes) of each candidate subsequence.

    Returns
    -------
    Counter[bytes]
        A mapping from each subsequence of size `length` to its count.
    """
    return Counter(data[i : i + length] for i in range(0, len(data) - length + 1))


def characterize_sequences(
    data: bytes,
    min_len: int,
    max_len: int,
    exp_len: int = 0,
    min_count: int = 2,
    max_count: int = 0,
    exp_count: int = 0,
    sort_by: str = "count",
):
    """
    Identify repeated byte sequences of various lengths and evaluate them
    as potential separators.

    Parameters
    -----------
    data : bytes
        The raw byte string to analyze.
    min_len : int
        Minimum length (in bytes) of candidate separators.
    max_len : int
        Maximum length (in bytes) of candidate separators.
    exp_len : int, optional
        Expected length of the separator sequence. Default is 0 (no expectation).
    min_count : int, optional
        Minimum number of occurrences for a candidate to be considered. Default is 2.
    max_count : int, optional
        Maximum number of occurrences for a candidate to be considered. Default is 0 (no limit).
    exp_count : int, optional
        Expected number of occurrences of the separator. Default is 0 (no expectation).
    sort_by : str, optional
        Field name to sort the results by. Default is "count".

    Returns
    -------
    results : dict
        Groups of entries keyed by the chosen `group_by` field.
    best_entry : dict
        The single highest-scoring candidate.
    """

    rows = []
    best_entry = None

    for sep_len in range(min_len, max_len + 1):
        counts = count_sequences(data, sep_len)

        for sep, sep_count in counts.items():
            if sep_count < min_count:
                continue
            if max_count and sep_count > max_count:
                continue

            # scoring components
            count_score = (
                1.0 - abs(sep_count - exp_count) / max(exp_count, 1) if exp_count else 1.0
            )
            len_score = 1.0 - abs(sep_len - exp_len) / max(exp_len, 1) if exp_len else 1.0

            # segment lengths between occurrences
            parts = data.split(sep)
            all_part_lengths = [len(v) for v in parts if v]
            if len(all_part_lengths) > 1:
                part_lengths, part_len_counts = np.unique(all_part_lengths, return_counts=True)
                if all(c == 1 for c in part_len_counts):
                    # all unique
                    common_part_len = int(np.median(part_lengths))
                    com_part_count = 1
                    part_score = 0.0
                else:
                    common_part_len = int(part_lengths[np.argmax(part_len_counts)])
                    com_part_count = int(np.max(part_len_counts))
                    part_score = com_part_count / len(all_part_lengths)
                # var_gap = float(np.var(all_part_lengths))
                # part_score = 1.0 / (1.0 + var_gap / ave_gap) if ave_gap else 1.0
            elif len(all_part_lengths) == 1:
                common_part_len = int(all_part_lengths[0])
                com_part_count = 1
                part_score = 0.0
            else:
                common_part_len = 0
                com_part_count = 0
                part_score = 0.0

            score = (count_score + part_score + len_score) / 3.0

            entry = {
                "score": round(score * 100, 2),
                "sep_count": sep_count,
                "separator": repr(sep),
                "sep_length": sep_len,
                "part_length": common_part_len,
                "parts_with_length": com_part_count,
                "count_diff": abs(sep_count + 1 - com_part_count),
                "part0_len": all_part_lengths[0] if all_part_lengths else 0,
                "null_parts_count": parts.count(b""),
                "raw_separator": sep,
            }

            rows.append(entry)

            if best_entry is None or entry["score"] > best_entry["score"]:
                best_entry = entry

    # Build a single DataFrame sorted by score
    df = pd.DataFrame(rows)

    if sort_by in df.columns:
        df = df.sort_values(sort_by, ascending=False).reset_index(drop=True)

    return df, best_entry


BASE_CODES = ["b", "B", "h", "H", "i", "I", "q", "Q", "f", "d"]
END_TYPES = ["<", ">", "="]
DECODES = ["ascii", "utf-8", "utf-16le", "utf-16be"]


def parse_bytes_all(data: bytes) -> dict:
    """
    Parse the first 16 bytes of a byte string into multiple candidate interpretations.
    For each base format code, try with END_TYPES <, >, = and repeat enough times
    to fill a multiple of the format size.
    Also run chardet to guess encoding and attempt decode.
    """
    data = data[:16]  # limit to first 16 bytes
    results = {"raw_hex": data.hex(), "length": len(data)}

    # base format codes to test
    for base in BASE_CODES:
        for prefix in END_TYPES:
            fmt = prefix + base
            size = struct.calcsize(fmt)
            repeat = -(-len(data) // size)  # ceiling division
            padded = (data * repeat)[: repeat * size]
            try:
                values = struct.unpack(prefix + (base * repeat), padded)
                results[fmt] = values
            except Exception:
                results[fmt] = None

    # text decodes with fixed encodings
    decode_opts = DECODES.copy()
    results["chardet"] = chardet.detect(data)
    if (
        results["chardet"]
        and "encoding" in results["chardet"]
        and results["chardet"]["encoding"] not in DECODES
    ):
        decode_opts = [str(results["chardet"]["encoding"])] + decode_opts
    for enc in decode_opts:
        try:
            results[enc] = data.decode(enc)
        except Exception:
            results[enc] = None

    # bit flags
    results["bit_flags"] = [bin(b)[2:].zfill(8) for b in data]

    return results


def search_numeric_candidates(data: bytes, fmt: str, target):
    """
    Scan a bytes object for all possible unpackings of a given struct format,
    sliding one byte at a time, and report how close each candidate is to `target`.

    Parameters
    ----------
    data : bytes
        The raw byte string to search.
    fmt : str
        The struct format string, e.g. '<i', '<H', '>I', 'f', etc.
        Endianness is *not* forced: whatever you pass is used directly.
    target : int or float
        The numeric value you are trying to locate.

    Returns
    -------
    pandas.DataFrame
        Columns:
            - offset: byte offset in `data` where unpacking was performed
            - value: unpacked numeric value at that position
            - delta: absolute difference from `target`
            - bytes_hex: the raw bytes (for that unpack) as hex

        Sorted by delta ascending (closest matches first).
    """
    size = struct.calcsize(fmt)
    records = []

    # iterate byte-by-byte so no possible alignment is missed
    for offset in range(0, len(data) - size + 1):
        chunk = data[offset : offset + size]
        try:
            value = struct.unpack(fmt, chunk)[0]
        except struct.error:
            # malformed chunk for this format; skip
            continue

        # compute closeness to target
        try:
            delta = abs(value - target)
        except TypeError:
            # non-numeric or incompatible target; skip
            continue

        records.append(
            {
                "offset": offset,
                "value": value,
                "delta": delta,
                "bytes_hex": repr(chunk),
            }
        )

    df = pd.DataFrame.from_records(records)
    if not df.empty:
        df = df.sort_values("delta", kind="mergesort").reset_index(drop=True)
    return df


def search_bytes_with_context(
    data: bytes,
    target: bytes | str,
    before: int = 100,
    after: int = 1000,
) -> dict[int, bytes]:
    """
    Search a byte string using a regex pattern and return contextual snippets.

    Parameters
    ----------
    data : bytes
        The byte string to search.
    pattern : bytes or compiled regex
        The regex pattern to search for (must be a bytes pattern).
    before : int
        Number of bytes to include before the match.
    after : int
        Number of bytes to include after the match.

    Returns
    -------
    Dict[int, bytes]
        Keys are match start positions.
        Values are the snippet: data[max(0, pos-before) : pos+after].
    """
    if isinstance(target, str):
        target = target.encode()

    pattern = re.compile(target)

    results = {}

    for m in pattern.finditer(data):
        pos = m.start()
        results[pos] = data[max(0, pos - before) : pos + after]

    return results
#%%

if __name__ == "__main__":
    # from gdoes_analysis.testing import DATA_DIR
    # from gdoes_analysis.parse_jys import main
    # file_path0 = DATA_DIR / "202309.jys"
    # file_path1 = DATA_DIR / "set4A r5_3.jys"
    # # file_path = DATA_DIR / "set4A r5_3.jys"
    # header0, dfs0, raw_df0, sections0, infos0 = main(file_path0)
    # header1, dfs1, raw_df1, sections1, infos1 = main(file_path1)
    # test_dec0 = {}
    # for key, val in infos0.items():
    #     if "prefix" in key:
    #         continue
    #     test_dec0[key] = parse_bytes_all(val[4:])
    # test_dec1 = {}
    # for key, val in infos1.items():
    #     if "prefix" in key:
    #         continue
    #     test_dec1[key] = parse_bytes_all(val[4:])
    # from gdoes_analysis.parse_jys import parse_body, create_body_dfs

    # crb_file = Path(
    #     r"D:\\Online\ASU Dropbox\Jacob Clenney\Work Docs\Data\Raw\GDOES\20250314\Data\2025-03\06\S0003167.crb"
    # )

    # crb_raw = crb_file.read_bytes()
    # # split_crb = crb_raw.split(b"\x01\x00\x00\x00")
    # sections, infos = parse_body(crb_raw, sep=b"\x01\x00\x00\x00")

    # dfs, raw_df = create_body_dfs(sections, infos)

    # root_folder = Path(r"C:\\quantum")
    # datasets = {f.name: f.read_bytes() for f in root_folder.glob("*.FIC", case_sensitive=False)}

    data_folder = Path(
        r"D:\\Online\ASU Dropbox\Jacob Clenney\Work Docs\Data\Raw\GDOES\20250314\Data\2025-03\14"
    )

    datasets = {f.stem: f.read_bytes() for f in data_folder.glob("*.crb")}

    results, best_entry = characterize_sequences(datasets["S0003224"], 2, 8, exp_count=46)
    
    sdf0_pth = Path(r"D:\\Online\ASU Dropbox\Jacob Clenney\Work Docs\Data\Analysis\Profilometry\GDOES\n15_r12_1_3.SDF")
    
    sdf1_pth = sdf0_pth.with_stem("n15_r12_2_3")
    
    sdf0_bytes = sdf0_pth.read_bytes()
    
    sdf0_text = sdf0_pth.read_text()
    
    sdf1_bytes = sdf1_pth.read_bytes()
    
    # res0 = datasets["Element.FIC"]
    # res00 = multi_split(res0, rb"(\x10.\x00....\x00\xff{3})", decode=False)  # b"\x10\x01\x00\xff"

    # print(*[s[:16] + b"  " + s[-20:] for s in res5[50:150]], sep="\n\n")

    # sample_data = b'\x01\x00\x00\x00\x02\x00\x00\x00Hello\x00World\x00'
    # seq_counts = count_sequences(sample_data, 4)
    # print("Sequence counts (length 4):", seq_counts)

    # characs = characterize_sequences(sample_data, 2, 6, exp_count=2)
    # print("Characterizations:", characs)

    # parsed = parse_bytes_all(sample_data)
    # print("Parsed bytes:", parsed)
