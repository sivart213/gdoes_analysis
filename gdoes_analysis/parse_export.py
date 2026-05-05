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
Created on Fri Dec 12 11:16:16 2025
"""

# %% Imports
from pathlib import Path

import pandas as pd

from gdoes_analysis.gd_file_parsing.parse_blk import load_blk_file
from gdoes_analysis.gd_file_parsing.parse_crb import load_crb_file
from gdoes_analysis.gd_file_parsing.parse_tools import (
    to_num,
    multi_split,
    group_by_len,
    make_elem_map,
    expand_headers,
    make_dataframe,
    rename_columns,
    recursive_apply,
    check_single_groups,
)


def load_export_info(path: str | Path, glob: str = "*.jye", num_dfs: bool = True):
    datasets = {f.stem: f.read_bytes() for f in Path(path).glob(glob)}
    dfs = {}
    parsed = {}
    for key, val in datasets.items():
        if key.endswith("desc"):
            rkey = "description"
            res = multi_split(val, b"\r\n", b"=")
            parsed[rkey] = res
            dfs[rkey] = pd.DataFrame(res, columns=["key", "value"]).set_index("key")
        else:
            rkey = key[-2:]  # LETTER_CODES.get(key[-2:], key)
            res = multi_split(val, b"\r\n", b"\t")
            res = expand_headers(res, "\x1b")
            res = recursive_apply(res, list, lambda x: x.strip())
            res = check_single_groups(group_by_len(res), prefix="\x1b")
            res = res[0] if len(res) == 1 else res
            parsed[rkey] = res
            try:
                dfs[rkey] = rename_columns(make_dataframe(*res))
            except Exception:
                pass
    if num_dfs:
        dfs = {key: to_num(df.copy()) for key, df in dfs.items()}
    return datasets, parsed, dfs


def load_exp_elem_map(source: str | Path | dict) -> pd.Series:
    """
    Load the element-line table directly from *el.jye inside the given folder.
    This bypasses load_export_info and parses only the needed file.
    """

    if isinstance(source, dict):
        return make_elem_map(source)
    else:
        # --- 1. Find the element-line file ------------------------------------
        _, _, dfs = load_export_info(Path(source), "*el.jye")
        return make_elem_map(dfs["el"])


def load_measurement_file(path: Path, elem_map: pd.Series | None = None) -> pd.DataFrame:
    """
    Load a measurement file (.blk or .crb) and return a DataFrame.
    elem_map is required only for .blk files.
    """
    suffix = path.suffix.lower()

    if suffix == ".blk":
        return load_blk_file(path, elem_map)
    else:
        return load_crb_file(path)


def load_export(
    path: str | Path,
) -> tuple[dict[str, pd.DataFrame], dict[str, pd.DataFrame | bytes]]:
    """
    Load all measurement files from a GDOES export folder.
    """
    path = Path(path)

    _, _, dfs = load_export_info(path)

    # elem_map = dfs["el"].set_index("Elem_Line_Key")
    elem_map = load_exp_elem_map(dfs)

    datasets = {}
    for row in dfs["re"].itertuples(index=False, name="Row"):
        f_pth = path / "Data" / str(row.Path)

        try:
            df = load_measurement_file(f_pth, elem_map=elem_map)
            df.attrs |= row._asdict()  # type: ignore
            datasets[f"{row.Sample_Name} {row.Sample_Name2}"] = df

        except Exception:
            datasets[f"{row.Sample_Name} {row.Sample_Name2}"] = f_pth.read_bytes()

    return dfs, datasets


if __name__ == "__main__":

    # import re

    # from gdoes_analysis.definitions import COL_NAMES, PART_TRANSLATIONS, DIRECT_TRANSLATIONS

    exp_folder = Path(r"D:\\Online\ASU Dropbox\Jacob Clenney\Work Docs\Data\Raw\GDOES\20250314")
    # exp_folder = Path(r"C:\\Users\j2cle\Desktop\New folder (6)")

    infosets, parsed, _ = load_export_info(exp_folder)

    inforaws = {key: val.decode(errors="ignore") for key, val in infosets.items()}

    dfs, datasets = load_export(exp_folder)

    # # elem_map = dfs["el"].set_index("Elem_Line_Key")
    # elem_map = load_exp_elem_map(dfs)
    # # elem_map = dfs["el"]["Elem_Name"].astype(str) + " "
    # # elem_map += dfs["el"]["Spectr_Line"].apply(lambda x: str(int(round(x))) if x else "")
    # # elem_map.index = dfs["el"]["Elem_Line_Key"]

    # datasets = {}
    # for row in dfs["re"].itertuples(index=False, name="Row"):
    #     f_pth = exp_folder / "Data" / str(row.Path)

    #     try:
    #         df = load_measurement_file(f_pth, elem_map=elem_map)
    #         df.attrs |= row._asdict()  # type: ignore
    #         datasets[f"{row.Sample_Name} {row.Sample_Name2}"] = df

    #     except Exception:
    #         datasets[f"{row.Sample_Name} {row.Sample_Name2}"] = f_pth.read_bytes()

    # datasets = {}
    # for row in dfs["re"].itertuples(index=False, name="Row"):
    #     f_pth = exp_folder / str("Data") / str(row.Path)
    #     data = f_pth.read_bytes()
    #     try:
    #         if f_pth.suffix.lower() == ".blk":
    #             df0, df_info = parse_blk_meas(data)
    #             names = elem_map[df0["Elem_Line_Key"]].reset_index(drop=True)
    #             df = pd.concat([names, df0.iloc[:, 1:], df_info], axis=1)
    #             df.attrs |= row._asdict()  # type: ignore
    #             datasets[f"{row.Sample_Name} {row.Sample_Name2}"] = df
    #         else:
    #             sections, infos = parse_body(data, sep=b"\x01\x00\x00\x00")
    #             dfs, raw_df = create_body_dfs(sections, infos)
    #             df = dfs[0]
    #             df.attrs |= row._asdict()  # type: ignore
    #             datasets[f"{row.Sample_Name} {row.Sample_Name2}"] = df
    #     except Exception:
    #         datasets[f"{row.Sample_Name} {row.Sample_Name2}"] = data

    # data_folder = Path(
    #     r"D:\\Online\ASU Dropbox\Jacob Clenney\Work Docs\Data\Raw\GDOES\20250314\Data\2025-03\14"
    # )

    # datasets = {f.stem: f.read_bytes() for f in data_folder.glob("*.crb")}

    # from gdoes_analysis.exploration import characterize_sequences

    # res0_spl, _ = characterize_sequences(
    #     datasets["1830 Calibration"], 1, 16, exp_count=46, min_count=5
    # )

    # res0 = multi_split(datasets["1830 Calibration"], b'\x00\x00\x00\xc0\x00\x00\x00\xc0', decode=False)

    # sections, infos = parse_body(datasets["S0003224"], sep=b"\x01\x00\x00\x00")

    # dfs, raw_df = create_body_dfs(sections, infos)

    # res01 = [r for r in res0 if len(r) != 8]
    # res02 = [(repr(r[18:]), repr(r[:18])) for r in res01[1:]]

    # res1_spl, _ = characterize_sequences(
    #     res0[1], 1, 16, exp_count=46, min_count=5
    # )

    # res1 = multi_split(datasets["1830 Calibration"], b'\x00\x00\x00\xc0\x00\x00\x00\xc0', b'\x03\x00\x00\x00', decode=False)

    # res2 = multi_split(datasets["1830 Calibration"], b'\x03\x00\x00\x00', decode=False)

    # print(*res01, sep="\n\n")
    # columns = set()
    # for key, val in parsed.items():
    #     if key == "description" or not isinstance(val, list):
    #         continue
    #     columns = columns | {re.sub(r"_\d{1,2}$", "", v) for v in val[0]}

    # for key, val in COL_NAMES.items():
    #     columns = columns | {re.sub(r"_\d{1,2}$", "", v) for v in val}

    # transl = set(DIRECT_TRANSLATIONS.keys()) | set(PART_TRANSLATIONS.keys())

    # diff = columns - transl

    # print(sorted(diff), sep=", ")

    # root_folder = Path(r"C:\\quantum")

    # datasets, parsed, dfs = load_info_files(root_folder, "*.FIC")

# for key, df in dfs.items():
#     print(key)
#     print(*[c for c in df.columns], sep="\n")
#     print()
