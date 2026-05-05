import re
import struct
import warnings
from pathlib import Path

import pandas as pd

from gdoes_analysis.gd_file_parsing.definitions import COL_NAMES
from gdoes_analysis.gd_file_parsing.parse_tools import multi_split, rename_columns

PACKINGS = {
    "Calibrat": struct.Struct("<2i b i b 2f"),
    "CORRELAT": struct.Struct("<2i f"),
    "Element": struct.Struct("<i 3sx f h h b 4sx 3f 16sx 12sx 12sx ? 4i"),
    "Elmetal": struct.Struct("<i 20sx i 5f 2d c"),
    "Eltetalo": struct.Struct("<20sx 3sx f h f"),
    "Eltmeth": struct.Struct("<3i 3sx f 4sx h 20sx 20sx 2f i f c f h 3f d b"),
    "Etalmeth": struct.Struct("<i 20sx"),
    "Etalon": struct.Struct("<20sx 20sx 3f 20sx 3sx b ? 3f ?"),
    "Layer": struct.Struct("<2i h sx 20sx 2f d 3f ?"),
    "LAYERELT": struct.Struct("<2i h 2f"),
    "listelt": struct.Struct("<3sx 2f i f"),
    "Methode": None,  # Encoded and cannot currently parse
    "MOLECUL": struct.Struct("<14sx 128sx f h " + "2sx " * 16 + "16h q"),
    "PMTType": struct.Struct("<12sx 2f 128sx"),
    "ProfMeth": struct.Struct("<3i"),
    "RAIE": struct.Struct("<2sx f h f b h " + "2sx " * 32 + "32c h " + "14sx " * 16 + "16c c f b"),
    "Raiemlcl": struct.Struct("<14sx f h f c 16sx"),
    "Recalibr": struct.Struct("<2i 2f 8sx 4sx"),
    "RES_CRATER": struct.Struct("<i h 3f 2i 5f"),
    "Res_elem": struct.Struct("<2i 3sx f i 2f 12sx"),
    "Res_prof": struct.Struct("<3i 4d"),
    "RES_SURF": struct.Struct("<i i i 12sx 12sx"),
    "Resultat": struct.Struct("<i 20sx 20sx i 20sx 8sx 4sx h 50sx q 12sx 12sx i h d 16f ?"),
    "Terms": struct.Struct("<16sx 20sx"),
    "Tr_param": struct.Struct("<4i 20sx h 200sx 16i"),
    "Tr_step": struct.Struct("<3i h"),
    "Treatmnt": struct.Struct("<i 20sx 200sx i"),
}

FIELD_SEP = {
    "Calibrat": rb"(\x10.[\x00\x01](?!\x00{4}).{4}\x00\xff{1})",
    "CORRELAT": rb"(\x10.\x00(?!\x00{4}).{4}\x00\xff{1})",
    "Element": rb"(\x10.\x00(?!\x00{4}).{4}\x00\xff{3})",
    "Elmetal": rb"(\x10.[\x00\x01](?!\x00{4}).{4}\x00\xff{2})",
    "Eltetalo": rb"(\x10.\x00(?!\x00{4}).{4}\x00\xff{1})",
    "Eltmeth": rb"(\x10.\x00(?!\x00{4}).{4}\x00\xff{3})",
    "Etalmeth": rb"(\x10.\x00(?!\x00{4}).{4}\x00\xff{1})",
    "Etalon": rb"(\x10.\x00(?!\x00{4}).{4}\x00\xff{2})",
    "Layer": rb"(\x10.\x00(?!\x00{4}).{4}\x00\xff{2})",
    "LAYERELT": rb"(\x10.\x00(?!\x00{4}).{4}\x00\xff{1})",
    "listelt": rb"(\x10[^\x00C]\x00(?!\x00{4}).{4}\x00\xff{1})",
    "Methode": rb"(\x10.\x00(?!\x00{4}).{4}\x00\xff{20})",
    "MOLECUL": rb"(\x10.\x00(?!\x00{4}).{4}\x00\xff{5})",
    "PMTType": rb"(\x10.\x00(?!\x00{4}).{4}\x00\xff{1})",
    "ProfMeth": rb"(\x10.\x00(?!\x00{4}).{4}\x00\xff{1})",
    "RAIE": rb"(\x10.\x00(?!\x00{4}).{4}\x00\xff{14})",
    "Raiemlcl": rb"(\x10.\x00(?!\x00{4}).{4}\x00\xff{1})",
    "Recalibr": rb"(\x10.\x00(?!\x00{4}).{4}\x00\xff{1})",
    "RES_CRATER": rb"(\x10.\x00(?!\x00{4}).{4}\x00\xff{2})",
    "Res_elem": rb"(\x10.\x00(?!\x00{4}).{4}\x00\xff{1})",
    "Res_prof": rb"(\x10.\x00(?!\x00{4}).{4}\x00\xff{1})",
    "RES_SURF": rb"(\x10.\x00(?!\x00{4}).{4}\x00\xff{1})",
    "Resultat": rb"(\x10.\x00(?!\x00{4}).{4}\x00\xff{4})",
    "Terms": rb"(\x10.\x00(?!\x00{4}).{4}\x00\xff{1})",
    "Tr_param": rb"(\x10.\x00(?!\x00{4}).{4}\x00\xff{3})",
    "Tr_step": rb"(\x10.\x00(?!\x00{4}).{4}\x00\xff{1})",
    "Treatmnt": rb"(\x10.\x00(?!\x00{4}).{4}\x00\xff{1})",
}


def parse_memo_block(mmo: bytes, offset: int):
    """
    Parse a memo block starting at `offset` in the full `.mmo` byte string.

    Block boundaries are determined ONLY by the next signature, not by
    total_len or used_len fields (which are informational only).

    Returns a dict with:
        - signature
        - total_length (informational)
        - used_length (informational)
        - chain_ptr
        - meta_a
        - meta_b
        - ascii_length
        - ascii_text
        - utf16_text
        - binary_tail
        - next_block_offset (validated)
        - raw_block
    """
    if not mmo or offset < 0 or offset >= len(mmo):
        return {
            "block_start": offset,
            "block_end": offset,
            "signature": repr(b""),
            "int_1": 0,
            "int_2": 0,
            "chain_ptr": repr(b""),
            "int_3": 0,
            "binary_pre1": repr(b""),
            "index": 0,
            "binary_pre2": repr(b""),
            "ascii_length": 0,
            "ascii_text": "",
            "binary_tail": repr(b""),
            "raw_block": repr(b""),
        }

    # --- 1. Validate signature ---
    sig = mmo[offset : offset + 2]
    if sig not in (b"\x07\xf4", b"\x08\xf4"):
        raise ValueError(f"Invalid memo signature at {offset}: {sig.hex()}")

    # Define block
    match = re.compile(rb"\x07\xf4|\x08\xf4").search(mmo, offset + 2)
    block_end = match.start() if match else len(mmo)
    raw_block = mmo[offset:block_end]

    # Extractions
    ascii_len = struct.unpack_from("<i", raw_block, 36)[0]

    return {
        "block_start": offset,
        "block_end": block_end,
        "signature": repr(sig),
        "int_1": struct.unpack_from("<i", raw_block, 2)[0],
        "int_2": struct.unpack_from("<i", raw_block, 6)[0],
        "chain_ptr": repr(raw_block[10:19]),
        "int_3": struct.unpack_from("<i", raw_block, 19)[0],
        "binary_pre1": repr(raw_block[23:26]),
        "index": struct.unpack_from("<i", raw_block, 26)[0],
        "binary_pre2": repr(raw_block[30:36]),
        "ascii_length": ascii_len,
        "ascii_text": raw_block[40 : 40 + ascii_len].decode("ascii", errors="ignore"),
        "binary_tail": repr(raw_block[40 + ascii_len :]),
        "raw_block": repr(raw_block),
    }


def parse_fic_table(
    path: str | Path,
    table_name: str,
    split_pattern: bytes | int | None = rb"(\x10.\x00(?!\x00{4})....\x00\xff{3})",
    unpack: bool = True,
    verbose: bool = False,
):
    """
    Generic HFSQL Classic .fic parser with row-level processors.

    Parameters
    ----------
    path : str | Path
        Directory containing the .fic/.mmo files.
    table_name : str
        Base name of the table (e.g., "Resultat").
    split_pattern : bytes | int | None
        Regex pattern used by multi_split to segment the .fic file.
        If an int N is provided, the pattern rb"(\x10.\x00(?!\x00{4}).{4}\x00\xff{N})" will be used.
        Examples:
            rb"(\x10.\x00.{4}\x00\xff{4})"  # for Resultat table
            rb"(\x10.\x00[^\x00]{4}\x00\xff{4})"
            rb"(\x10.\x00(?!\x00{4}).{4}\x00\xff{3})"
            rb"(\x10[^\x00]\x00(?!\x00{4}).{4}\x00\xff{3})"
    verbose : bool
        If True, warnings about extra bytes will be shown.

    Returns
    -------
    df_rows : pd.DataFrame
        Parsed rows.
    df_info : pd.DataFrame
        Per-row metadata.
    """

    path = Path(path)

    # Load all files matching table_name.*
    datasets = {f.suffix.lower(): f.read_bytes() for f in path.glob(f"{table_name}.*")}

    if ".fic" not in datasets:
        raise FileNotFoundError(f"No {table_name}.fic found in {path}")

    mmo_bytes = datasets.get(".mmo")  # may be None

    # Split the .fic into record chunks
    if split_pattern is None:
        split_pattern = FIELD_SEP.get(table_name, 3)

    if isinstance(split_pattern, int):
        split_pattern = (
            rb"(\x10.\x00(?!\x00{4}).{4}\x00\xff{" + str(split_pattern).encode() + rb"})"
        )

    chunks = multi_split(datasets[".fic"], split_pattern, decode=False)
    if len(chunks) < 3:
        return pd.DataFrame(), pd.DataFrame(), datasets

    datasets["header"] = chunks[0]

    # External mappings
    fmt_struct = PACKINGS.get(table_name) if unpack else None

    row_size = fmt_struct.size if fmt_struct is not None else 0

    # Optional rowprocessor
    rowprocessor = PROCESSORS.get(table_name)

    parsed_rows = []
    parsed_info = []

    # Iterate through every "data" chunk (skip prefix chunks)
    warn_str = ""
    for i in range(2, len(chunks), 2):
        raw = chunks[i]

        if len(raw) < row_size:
            raise ValueError(f"Record at index {i//2} is too short: {len(raw)} bytes")

        info = {
            "Rec #.": i // 2,
            "raw_prefix": repr(chunks[i - 1]),
            "raw_bytes": repr(raw),
        }

        if len(raw) > row_size and fmt_struct is not None:
            if not warn_str:
                warn_str = f"{table_name}: raw chunks longer than expected by {len(raw) - row_size} bytes "
            info["extra_bytes"] = repr(raw[row_size:])

        # Unpack the row
        if fmt_struct is not None:
            row = list(fmt_struct.unpack_from(raw, 0))

            # Normalize bytes → strings
            row = [
                x.decode(errors="ignore").strip() if isinstance(x, (bytes, bytearray)) else x
                for x in row
            ]

            # Optional table-specific rowprocessor
            if rowprocessor is not None:
                row, info = rowprocessor(row, info, mmo_bytes)
        else:
            row = [len(chunks[i - 1]), info["raw_prefix"], len(raw), info["raw_bytes"]]

        # Insert record number at front
        row.insert(0, info["Rec #."])

        parsed_rows.append(row)
        parsed_info.append(info)

    if verbose and warn_str:
        warnings.warn(warn_str)

    # Build DataFrames
    colnames = COL_NAMES.get(table_name, [])
    if colnames and colnames[0] != "Rec #.":
        colnames = ["Rec #."] + colnames

    if len(colnames) != len(parsed_rows[0]):
        colnames = ["Rec #.", "raw_prefix_len", "raw_prefix", "raw_bytes_len", "raw_bytes"]
        if fmt_struct is not None:
            colnames = ["Rec #."] + [f"col_{i}" for i in range(len(parsed_rows[0]) - 1)]

    df_rows = rename_columns(pd.DataFrame(parsed_rows, columns=colnames))
    df_info = pd.DataFrame(parsed_info)

    return df_rows, df_info, datasets


def resultat_process(row, info, mmo_bytes):
    # Convert date fields
    row[5] = pd.to_datetime(row[5], format="%Y%m%d").date()
    row[6] = pd.to_datetime(row[6], format="%H%M").time()
    info["RECLEUNIK"] = row[0]

    # Resolve memo pointer
    memo_data = parse_memo_block(mmo_bytes, row[9])
    info |= {f"mmo_{k}": v for k, v in memo_data.items()}
    row[9] = memo_data.get("ascii_text", "")

    return row, info


def element_process(row, info, mmo_bytes):
    # Convert date fields
    row.append(", ".join([str(row[i]) for i in (6, 1)]))

    return row, info


def molecul_process(row, info, mmo_bytes):
    # Convert date fields
    # Resolve memo pointer
    memo_data = parse_memo_block(mmo_bytes, row[-1])
    info |= {f"mmo_{k}": v for k, v in memo_data.items()}
    row[-1] = memo_data.get("ascii_text", "")

    return row, info


def eltmeth_process(row, info, mmo_bytes):
    # Convert date fields
    row[13] = int(row[13])
    row.append(", ".join([str(row[i]) for i in (1, 15)]))
    return row, info


def eltetalo_process(row, info, mmo_bytes):
    # Convert date fields
    row.append(", ".join([str(row[i]) for i in (0, 1)]))

    return row, info


def raie_process(row, info, mmo_bytes):
    # Convert date fields
    row.append(", ".join([str(row[i]) for i in (0, 1, 2)]))

    return row, info


def elmetal_process(row, info, mmo_bytes):
    # Convert date fields
    row.append(", ".join([str(row[i]) for i in (1, 2)]))

    return row, info


def correlat_process(row, info, mmo_bytes):
    # Convert date fields
    row.append(", ".join([str(row[i]) for i in (0, 1)]))

    return row, info


def layer_process(row, info, mmo_bytes):
    # Convert date fields
    row.append(", ".join([str(row[i]) for i in (1, 2)]))

    return row, info


def layerelt_process(row, info, mmo_bytes):
    # Convert date fields
    row.append(", ".join([str(row[i]) for i in (0, 2)]))

    return row, info


def raiemlcl_process(row, info, mmo_bytes):
    # Convert date fields
    row.append(", ".join([str(row[i]) for i in (0, 1, 2)]))

    return row, info


def recalibr_process(row, info, mmo_bytes):
    # Convert date fields
    dt = pd.to_datetime(f"{row[4]} {row[5]}", format="%Y%m%d %H%M")
    row[4] = dt.date()
    row[5] = dt.time()
    # row[4] = pd.to_datetime(row[4], format="%Y%m%d").date()
    # row[5] = pd.to_datetime(row[5], format="%H%M").time()
    row.append(dt)

    return row, info


def terms_process(row, info, mmo_bytes):
    # Convert date fields
    row.append(", ".join([str(row[i]) for i in (0, 1)]))

    return row, info


PROCESSORS = {
    "Resultat": resultat_process,
    "Element": element_process,
    "MOLECUL": molecul_process,
    "Eltmeth": eltmeth_process,
    "Eltetalo": eltetalo_process,
    "RAIE": raie_process,
    "Elmetal": elmetal_process,
    "CORRELAT": correlat_process,
    "Layer": layer_process,
    "LAYERELT": layerelt_process,
    "Raiemlcl": raiemlcl_process,
    "Recalibr": recalibr_process,
    "Terms": terms_process,
}
