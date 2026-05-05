from pathlib import Path

import numpy as np
import pandas as pd

from gdoes_analysis.gd_file_parsing.parse_jy import parse_jy_file
from gdoes_analysis.gd_file_parsing.parse_jys import main as parse_jys_file


def compare_decoded_to_reference(
    decoded_df: pd.DataFrame,
    header: dict,
    reference_df: pd.DataFrame,
) -> dict:
    """
    Compare a decoded DataFrame against a reference DataFrame.

    Parameters
    ----------
    decoded_df : pd.DataFrame
        The DataFrame built from the text file.
    header : dict
        Parsed header with keys "section_names" and "signal_table"["NOMELEM"].
    reference_df : pd.DataFrame
        The reference DataFrame to compare against.

    Returns
    -------
    results : dict
        Mapping of reference column -> comparison result dict with keys:
        {"status": "match"/"mismatch"/"missing"/"length mismatch",
         "section_name": ..., "ref_name": ...}
    """

    # map reference names -> decoded names
    name_map: dict[str, str] = {
        k: v for k, v in zip(header["signal_table"]["NOMELEM"], header["section_names"])
    }

    results = {}

    for ref_col in reference_df.columns:
        section_name = name_map.get(ref_col, ref_col)

        if section_name not in decoded_df.columns:
            results[ref_col] = {
                "status": "missing",
                "section_name": section_name,
                "ref_name": ref_col,
            }
            continue

        dcol = decoded_df[section_name].to_numpy()
        rcol = reference_df[ref_col].to_numpy()

        if len(dcol) != len(rcol):
            results[ref_col] = {
                "status": "length mismatch",
                "section_name": section_name,
                "ref_name": ref_col,
                "decoded_len": len(dcol),
                "reference_len": len(rcol),
            }
            continue

        # compute closeness metrics
        abs_diff = np.abs(dcol - rcol)
        with np.errstate(divide="ignore", invalid="ignore"):
            rel_diff = abs_diff / np.where(rcol != 0, np.abs(rcol), np.nan)

        results[ref_col] = {
            "status": "ok",
            "section_name": section_name,
            "ref_name": ref_col,
            "abs_diff": float(f"{np.nanmax(abs_diff):.4g}"),
            "rel_diff": float(f"{np.nanmax(rel_diff):.4g}"),
        }

    return results


def main(jys_path: str | Path, jy_path: str | Path, body_sep: bytes = b"\x01\x00\x00\x00"):
    header, df, _, _, _ = parse_jys_file(jys_path, body_sep=body_sep)
    _, ref_df = parse_jy_file(jy_path)

    results = compare_decoded_to_reference(df, header, ref_df)
    return results


if __name__ == "__main__":
    from gdoes_analysis.testing import DATA_DIR

    results = main(DATA_DIR / "202309.jys", DATA_DIR / "202309_conv.jy")

    for col, res in results.items():
        print(col, res)

    results = main(DATA_DIR / "set4A r5_3.jys", DATA_DIR / "set4a_r5_conv.jy")

    for col, res in results.items():
        print(col, res)
