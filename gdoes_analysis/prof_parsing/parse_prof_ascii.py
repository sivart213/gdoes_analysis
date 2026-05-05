import re
import warnings
from pathlib import Path

import numpy as np

from gdoes_analysis.prof_parsing.definitions import ASCII_DEFAULTS, ASCII_DEFAULT_TABLE
from gdoes_analysis.parse_tools.general_tools import oldest_timestamp, restructure_surf_dict

FMT_CODE_MAPS = [
    {0: "grid (no axis)", 1: "xyz (pixel)", 2: "xyz (real)"},
    {0: "waves", 1: "nm"},
]


def _wyko_parse_raw(text: str, keep_raws: bool = False, force: bool = False) -> dict:
    """
    Parse a Wyko ASCII file (any format) into a structured dict.

    Parameters
    ----------
    text : str
        The full text content of the Wyko ASCII file.
    keep_raws : bool, optional
        Whether to keep raw text parts in the output, by default False.
    force : bool, optional
        Whether to force parsing even on errors, by default False.
    Returns
    -------
    dict
        Parsed Wyko ASCII data and metadata.
    """
    data = ASCII_DEFAULTS.copy()
    # --- Split header and body at raw_data line ---
    # text = path.read_text(encoding="latin1", errors="ignore")
    try:
        parts = re.split(r"(RAW_DATA.*)\n", text, maxsplit=1)
        if len(parts) != 3:
            raise ValueError("RAW_DATA section not found")

        header_text, raw_data_line, body_text = parts

        if keep_raws:
            data["raw_parts"] = parts.copy()

        # --- Parse header lines ---
        lines = [ln.strip() for ln in header_text.splitlines() if ln.strip()]

        fmt_match = re.search(r"(\d)([,\s\t])(\d).(\d)", lines[0].strip())
        if not fmt_match:
            raise ValueError("Cannot parse the format from the first line")

        data["prologue"] = lines[0].split("Format")[0].strip()
        data["formats"] = fmts = [int(fmt_match.group(i)) for i in (1, 3, 4)]
        data["separator"] = sep = fmt_match.group(2)

        if fmts[0] not in FMT_CODE_MAPS[0]:
            raise ValueError(f"Unknown Wyko ASCII format code: {fmts[0]}")

        data["x_points"] = int(lines[1].split(sep)[-1])
        data["y_points"] = int(lines[2].split(sep)[-1])
        data["source_format"] = "wyko-ascii: " + FMT_CODE_MAPS[0].get(fmts[0], "unknown")
        data["source_z_unit"] = FMT_CODE_MAPS[1].get(fmts[1], "unknown")

        if not lines[3].lower().startswith("block name"):
            raise ValueError(f"Expected 'Block Name{sep}Type{sep}Length{sep}Value' row")

        data["table"] = {k: v.copy() for k, v in ASCII_DEFAULT_TABLE.items()}

        for line in lines[4:]:  # Skip first 3 + block header
            parts = line.split(sep) + [""] * 4  # pad to avoid index error
            data["table"][parts[0].lower()] = {
                "type": int(parts[1]),
                "length": int(parts[2]),
                "value": float(parts[3]),
            }
            data[parts[0].lower()] = float(parts[3])

        # --- Normalize body for numpy and parse ---
        rsep = re.escape(sep)
        if fmts[0] == 0:
            null = rf"(?<={rsep})(?:Bad)?(?={rsep})"
            eol = rf"{rsep}\n+"
        else:
            null = rf"(?<={rsep})(?:Bad)?(?=\n)"
            eol = r"\n"

        body_clean = re.sub(eol, sep, re.sub(null, "nan", body_text))

        try:
            data_vals = np.fromstring(body_clean, sep=sep, dtype=float)
        except ValueError as exc:
            data["warnings"] = [f"Failed to parse data values: {exc}"]
            data_vals = np.array([])

        # --- Parse raw_data line ---
        parts = raw_data_line.split(sep) + [""] * 4
        data["table"]["raw_data"] = {
            "type": int(parts[1]),
            "length": int(parts[2]),
        }
        data["raw_data"] = data_vals

        if int(parts[2]) / 4 != data["x_points"] * data["y_points"]:
            data.setdefault("warnings", [])
            data["warnings"].append("raw_data length does not match X Size * Y Size")

    except Exception as exc:
        if not force:
            raise exc
        warnings.warn(f"Failed to parse Wyko ASCII file: {exc}")
        data["error"] = str(exc)

    return data


def _wyko_build_arrays(values: np.ndarray, info: dict, keep_raws: bool = False) -> dict:
    """
    Build points + axes for Wyko ASCII structures 0, 1, 2.

    Parameters
    ----------
    values : np.ndarray
        The raw data values from the Wyko ASCII file.
    info : dict
        The parsed metadata information from the Wyko ASCII file.
    keep_raws : bool, optional
        Whether to keep raw arrays in the output, by default False.
    Returns
    -------
    dict
        Structured arrays and scaling information.
    """

    # Extract structure code from Format line
    # Example: "Wyko ASCII Data File Format 0,1,1"
    Nx = info["x_points"]
    Ny = info["y_points"]

    x_scale = info["pixel_size"]
    y_scale = x_scale * info["aspect"]
    z_scale = 1.0 if info["formats"][1] else info["wavelength"]

    if "grid" in info["source_format"]:
        # grid structure (no axis provided)
        if values.size != Nx * Ny:
            raise ValueError("Data size mismatch for grid format")
        xs = np.arange(Nx)
        ys = np.arange(Ny)
        zs = values.reshape((Nx, Ny)).T

    else:
        # xyz structure
        if values.size != Nx * Ny * 3:
            raise ValueError("Data size mismatch for xyz format")
        arr = values.reshape((-1, 3))

        xs = np.unique(arr[:, 0])
        ys = np.unique(arr[:, 1])
        zs = arr[:, 2].reshape((Nx, Ny)).T

    x_array = xs.copy()
    y_array = ys.copy()
    z_array = zs.copy() * z_scale

    if not info["source_format"].endswith("(real)"):
        x_array = x_array * x_scale
        y_array = y_array * y_scale

    # --- Finalize shared fields ---
    res = {
        "z_array": z_array,
        "x_array": x_array,
        "y_array": y_array,
        "x_scale": x_scale,
        "y_scale": y_scale,
        "z_scale": z_scale,
        "x_offset": float(x_array.min()),
        "y_offset": float(y_array.min()),
        "z_offset": float(z_array.min()),
    }

    if keep_raws:
        res["data_unscaled"] = {"z_array": zs, "x_array": xs, "y_array": ys}
    return res


def read_wyko_ascii(
    path: Path | str,
    keep_raws: bool = False,
    parse_array: bool = True,
    force: bool = False,
    **kwargs,
) -> dict:
    """
    Read and parse a Wyko ASCII file into a structured dict.

    Parameters
    ----------
    path : Path | str
        Path to the Wyko ASCII file.
    keep_raws : bool, optional
        Whether to keep raw text parts and arrays in the output, by default False.
    parse_array : bool, optional
        Whether to parse and build data arrays, by default True.
    force : bool, optional
        Whether to force parsing even on errors, by default False.
    Returns
    -------
    dict
        Parsed Wyko ASCII data and metadata.
    """
    path = Path(path)
    res = ASCII_DEFAULTS.copy()

    text = path.read_text(encoding="latin1", errors="ignore")

    parsed = _wyko_parse_raw(text, keep_raws=keep_raws, force=force)

    values = parsed["raw_data"].copy()
    if parse_array and "error" not in parsed and values.size > 0:
        if not keep_raws:
            parsed.pop("raw_data")
        # Dispatch — pass the *lines* list, not the path
        res |= _wyko_build_arrays(values, parsed, keep_raws=keep_raws)
        # Metadata only — no geometry, no reshaping, no Nx/Ny

    res |= parsed

    # --- Metadata ---
    res["filename"] = path.name
    res["path"] = str(path)
    res.setdefault("timestamp", oldest_timestamp(path))

    res |= kwargs

    if not keep_raws:
        res = restructure_surf_dict(res)

    return res


if __name__ == "__main__":
    gd_folder = Path(
        r"D:\\Online\ASU Dropbox\Jacob Clenney\Work Docs\Data\Analysis\Profilometry\GDOES"
    )

    ascii_res = read_wyko_ascii(gd_folder / "n15_r12_1_1_1.ASC")  #  "n15_r12_2_1_1.ASC"

    # ascii_results = {
    #     f.stem: read_wyko_ascii(f) for f in ascii_folder.glob("n15_r12*.ASC")
    # }

    # pth_1 = Path(
    #     r"D:\\Online\ASU Dropbox\Jacob Clenney\Work Docs\Data\Analysis\Profilometry\GDOES\Spot 1.ASC"
    # )
    # pth_2 = Path(
    #     r"D:\\Online\ASU Dropbox\Jacob Clenney\Work Docs\Data\Analysis\Profilometry\GDOES\Spot 12.ASC"
    # )

    # asc1 = read_wyko_ascii(pth_1)
    # asc2 = read_wyko_ascii(pth_2)
