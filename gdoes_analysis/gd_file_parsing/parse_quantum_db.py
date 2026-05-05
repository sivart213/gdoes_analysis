from pathlib import Path

import pandas as pd

from gdoes_analysis.prof_parsing.parse_sur import get_sur_df
from gdoes_analysis.gd_file_parsing.parse_blk import load_blk_file
from gdoes_analysis.gd_file_parsing.parse_crb import load_crb_file
from gdoes_analysis.gd_file_parsing.parse_fic import FIELD_SEP, parse_fic_table
from gdoes_analysis.gd_file_parsing.parse_tools import multi_split, make_elem_map


def split_stream(
    data: bytes,
    sep: bytes = rb"([\x01\x02\x03]\x00\x00\x00)",
) -> tuple[bytes, list[list[bytes]], list[list[bytes]], list[bytes]]:
    """
    Returns:
      header: bytes
      data_rows: list[list[bytes]]
      four_rows: list[list[bytes]]
      eight_separators: list[bytes]
    """
    if not sep.startswith(b"(") or not sep.endswith(b")"):
        sep = rb"(" + sep + rb")"

    segments = multi_split(data, sep, decode=False)
    # --- 1. Pre-count totals over entire stream -----------------------------
    total4 = sum(len(s) == 4 for s in segments)
    total816 = sum(len(s) in (8, 16) for s in segments)

    remaining4 = total4
    remaining816 = total816

    # --- 2. Find header boundary by comparing remaining counts -------------
    header_end = 0  # index AFTER the last header segment

    for idx, seg in enumerate(segments):
        L = len(seg)

        if L in (8, 16):
            remaining816 -= 1
        elif L == 4:
            remaining4 -= 1

            # When remaining counts balance, we've likely stripped all header
            if remaining4 + 1 == remaining816:
                header_end = idx
                break
        if remaining4 < total4 / 2:
            raise ValueError("Header parsing failed.  Recomend re-evaluation of separators")

    header = b"".join(segments[:header_end])
    body_segments = segments[header_end:]

    # --- 3. Parse body into rows, 4-byte lists, and 8-byte separators ------
    data_rows = []
    info_data = []
    four_rows = []

    current_row = []
    current_four = []

    for seg in body_segments:
        L = len(seg)

        if L == 16:
            # Start a new row
            if current_row:
                current_row.append(seg[:8])
                data_rows.append(current_row)
                four_rows.append(current_four)
            else:
                current_row = [seg[:8]]
            info_data.append(seg[8:])
            current_row = []
            current_four = []

        elif L == 8:
            # Always row data
            if not current_row:
                current_row = [seg[:8]]
            else:
                current_row.append(seg)

        elif L == 4:
            # Always a separator for the current row
            if not current_four:
                current_four.append(seg)
            else:
                current_four.append(seg)

        else:
            raise ValueError(f"Unexpected segment length {L}")

    # Append last row
    if current_row:
        data_rows.append(current_row)
        four_rows.append(current_four)

    return header, data_rows, four_rows, info_data


def load_quantum_info(path: str | Path = r"C:\\quantum", glob: str = "*.FIC") -> dict:
    root_folder = Path(path)
    fics = list(root_folder.glob(glob, case_sensitive=False))
    if glob.lower()[-3:] != "fic":
        fics = [f for f in fics if f.suffix.lower() == ".fic"]

    quantum = {
        "dataframes": {},
        "info": {},
        "raws": {},
    }
    for path in fics:  # PACKINGS.keys(): rename_columns
        key = path.stem
        try:
            df, info, raws = parse_fic_table(root_folder, key, FIELD_SEP.get(key, 3), True, True)
            if not df.empty:
                quantum["dataframes"][key] = df
            quantum["info"][key] = info
            quantum["raws"][key] = raws
        except Exception as exc:
            print(f"Error parsing {key}: {exc}")
            df, info, raws = parse_fic_table(root_folder, key, FIELD_SEP.get(key, 1), False)
            if not df.empty:
                quantum["dataframes"][key] = df

            quantum["info"][key] = info
            quantum["raws"][key] = raws

    return quantum


def load_fic_elem_map(source: str | Path | dict) -> pd.Series:
    """
    Load the element-line table directly from *el.jye inside the given folder.
    This bypasses load_export_info and parses only the needed file.
    """

    if isinstance(source, dict):
        if "dataframes" in source:
            return make_elem_map(source["dataframes"]["Element"])
        return make_elem_map(source["Element"])
    else:
        # --- 1. Find the element-line file ------------------------------------
        df, _, _ = parse_fic_table(Path(source), "Element")
        return make_elem_map(df)


def load_meas_file(path: Path, elem_map: pd.Series | None = None) -> pd.DataFrame | bytes:
    """
    Load a measurement file (.blk or .crb) and return a DataFrame.
    elem_map is required only for .blk files.
    """
    suffix = path.suffix.lower()

    if suffix == ".blk":
        return load_blk_file(path, elem_map)
    elif suffix == ".crb":
        return load_crb_file(path)
    elif suffix == ".sur":
        return get_sur_df(path)
    else:
        try:
            return load_crb_file(path)
        except Exception:
            return path.read_bytes()


# %%
if __name__ == "__main__":
    from gdoes_analysis.exploration import characterize_sequences  # noqa: F401

    root_folder = Path(r"C:\\quantum")

    quantum = load_quantum_info(root_folder, "*.FIC")

    # %%
    resultat = quantum["dataframes"]["Resultat"]
    my_all = resultat[resultat["Operator"].isin({"JB", "JC", "JCLENNEY"})]
    other_types = resultat[~resultat["Path"].str.lower().str.endswith((".blk", ".crb"))]

    elem_map = load_fic_elem_map(quantum)

    # %%
    # for row in pd.concat([my_all, other_types]).itertuples(index=False, name="Row"):  # type: ignore
    data_dfs = {}
    for df in [other_types]:
        for row in df.itertuples(index=False, name="Row"):  # type: ignore
            if not str(row.Path):
                continue
            key = f"{row.Sample_Name} {row.Sample_Name2}"
            f_pth = root_folder / str("data") / str(row.Path)
            try:
                data_dfs[key] = load_meas_file(f_pth, elem_map=elem_map)
            except Exception as exc:
                print(f"Error loading {key}: {exc}")
                data_dfs[key] = f_pth.read_bytes()

    # from gdoes_analysis.exploration import search_numeric_candidates

    # num_matches = {}
    # targs = {
    #     "Points": 160,
    #     "Lines": 1603,
    #     "X Step": 49687498752,
    #     "Y Step": 4984419840,
    #     "X Offset": -3974999834624,
    #     "Y Offset": -3995012431872,
    #     "Height 1": -4437724672,
    #     "Height 2": 4437724672,
    #     "Val 00": -3386748160,
    #     "Val 01": -3388246784,
    #     "Val 10": -3379570944,
    # }

    # for key, targ in targs.items():
    #     fmt = "<i" if key in {"Points", "Lines"} else "<f"
    #     num_matches[key] = search_numeric_candidates(data_dfs["N15_r1 "][:5000], fmt, targ)

        # char_seq[key], _ = characterize_sequences(
        #     data_bytes[key], 1, 16, exp_count=46, min_count=5
        # )

    # test_head, test_rows, test_info = parse_blk_meas(data_bytes["1830 r5"])

    # val = 589.590
    # num_match = {}
    # for key in data_bytes:
    #     num_match[key] = search_numeric_candidates(data_bytes[key], "<f", val)
    #     if num_match[key]["delta"].min() <= 1e-4:
    #         print(f"{val} match in {key}")

    # # res0_spl, _ = characterize_sequences(datasets["1830 r5"], 1, 16, exp_count=46, min_count=5)

    # res0 = multi_split(data_bytes["1830 r5"], b"\x00\x00\x00\xc0\x00\x00\x00\xc0", decode=False)

    # res1 = multi_split(
    #     data_bytes["1830 r5"],
    #     b"\x00\x00\x00\xc0\x00\x00\x00\xc0",
    #     b"\x03\x00\x00\x00",
    #     decode=False,
    # )

    # res2 = multi_split(data_bytes["1830 r5"], rb"([\x01\x02\x03]\x00\x00\x00)", decode=False)

    # header2, data_rows2, four_rows2, info_data2 = split_stream(
    #     data_bytes["1830 r5"], rb"([\x01\x02\x03]\x00\x00\x00)"
    # )

    # data_rows2_dec = [[struct.unpack("<2f", d) for d in data] for data in data_rows2]
    # four_rows2_repr = [[repr(d) for d in data] for data in four_rows2]
    # info_data2_repr = [repr(d) for d in info_data2]

    # (
    #     len(data_bytes["1830 r5"])
    #     - len(header2)
    #     - sum(sum(len(b) for b in row) for row in data_rows2)
    #     - sum(sum(len(b) for b in row) for row in four_rows2)
    #     - len(info_data2) * 8
    # )

    # res3 = multi_split(data_bytes["CU-NACL3 r4"], rb"([\x01\x02\x03]\x00\x00\x00)", decode=False)

    # res4 = multi_split(data_bytes["GTA r2"], rb"([\x01\x02\x03]\x00\x00\x00)", decode=False)

    # res21 = [r for r in res2 if len(r) != 8]

    # res31 = [r for r in res3 if len(r) != 8]

    # res41 = [r for r in res4 if len(r) != 8]

    # print(*[r[8:] for r in res21[2:]], sep="\n")

    # print()

    # print(*[r[8:] for r in res31[2:]], sep="\n")

    # print()

    # print(*[r[8:] for r in res41[2:]], sep="\n")

    # test_split = []
    # for arr in res2[2:]:
    #     test_split.append(struct.unpack_from("<2f", arr, 0))

    # df_res1, df_res1_info, raws1 = parse_fic_table(root_folder, "Resultat", 4)
    # df_res2, df_res2_info, raws2 = parse_fic_table(root_folder, "Element", 3)
    # df_res3, df_res3_info, raws3 = parse_fic_table(root_folder, "Tr_param", 3)
    # df_res4, df_res4_info, raws4 = parse_fic_table(root_folder, "Eltmeth", 3)
    # df_res5, df_res5_info, raws5 = parse_fic_table(root_folder, "MOLECUL", 5)
