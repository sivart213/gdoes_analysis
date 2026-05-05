import struct
from pathlib import Path
from datetime import datetime

import numpy as np

from gdoes_analysis.prof_parsing.definitions import SDF_DEFAULTS, SDF_RENAME_MAP
from gdoes_analysis.parse_tools.general_tools import oldest_timestamp, restructure_surf_dict

BIN_HDR_FMT = "<8s10s12s12s2h4d3b"
BIN_HDR_SIZE = struct.calcsize(BIN_HDR_FMT)

SDF_DTYPE_MAP = {
    5: np.int16,
    6: np.int32,
    7: np.float64,
}


HEADER_DTYPES = {k: type(v) for k, v in SDF_DEFAULTS.items()}


def _parse_ascii_header(text: str) -> dict:
    """Parse SDF ASCII header into a dict."""
    header = SDF_DEFAULTS.copy()
    for line in text.splitlines():
        if "=" not in line:
            continue
        key, val = line.split("=", 1)
        key = key.strip()
        val = val.strip()

        if "Date" in key:
            try:
                header[key] = datetime.strptime(val, "%d%m%Y%H%M")
            except ValueError:
                header[key] = datetime.strptime(val[-4:], "%H%M")
        else:
            header[key] = HEADER_DTYPES.get(key, str)(val)

    if header["DataType"] not in SDF_DTYPE_MAP:
        raise ValueError(f"Unknown SDF DataType: {header['DataType']}")

    return header


def read_sdf_ascii(raw: bytes) -> dict:
    """
    Read SDF ASCII data from raw bytes.

    Parameters
    ----------
    raw : bytes
        The full raw content of the SDF ASCII file.
    Returns
    -------
    dict
        Parsed SDF ASCII data and metadata.
    """
    text = raw.decode("latin1")

    # Split header and body
    if "\r\n*\r\n" in text:
        header_text, body_text = text.split("\r\n*\r\n")[:2]
    elif "\n*\n" in text:
        header_text, body_text = text.split("\n*\n")[:2]
    else:
        raise ValueError("ASCII SDF missing '*' separator")

    header = _parse_ascii_header(header_text)

    dtype = SDF_DTYPE_MAP[int(header["DataType"])]

    values = np.fromstring(body_text, sep=" ", dtype=dtype)

    return {
        **header,
        "points": values,
        "dtype": dtype,
        "source_format": "sdf-ascii",
    }


def _parse_binary_header(raw: bytes) -> dict:
    """Parse SDF binary header into a dict."""
    header = SDF_DEFAULTS.copy()

    fields = struct.unpack("<8s10s12s12s2h4d3b", raw)

    if fields[11] not in SDF_DTYPE_MAP:
        raise ValueError(f"Unknown SDF DataType code: {fields[11]}")

    header |= {
        "signature": fields[0].decode("latin1").rstrip("\x00"),
        "ManufacID": fields[1].decode("latin1").rstrip("\x00"),
        "CreateDate": fields[2].decode("latin1").rstrip("\x00"),
        "ModDate": fields[3].decode("latin1").rstrip("\x00"),
        "NumPoints": fields[4],
        "NumProfiles": fields[5],
        "Xscale": fields[6],
        "Yscale": fields[7],
        "Zscale": fields[8],
        "Zresolution": fields[9],
        "Compression": fields[10],
        "DataType": fields[11],
        "CheckType": fields[12],
    }
    return header


def read_sdf_binary(raw: bytes, hdr_size: int = 81) -> dict:
    """
    Read SDF binary data from raw bytes.

    Parameters
    ----------
    raw : bytes
        The full raw content of the SDF binary file.
    Returns
    -------
    dict
        Parsed SDF binary data and metadata.
    """
    header = _parse_binary_header(raw[:hdr_size])

    dtype = SDF_DTYPE_MAP[header["DataType"]]

    values = np.frombuffer(
        raw[hdr_size:], dtype=dtype, count=header["NumPoints"] * header["NumProfiles"]
    )

    return {
        **header,
        "points": values,
        "dtype": dtype,
        "source_format": "sdf-binary",
    }


def _sdf_build_arrays(header: dict, points: np.ndarray, keep_raws: bool = False) -> dict:
    """
    Convert raw SDF points into physical units using header scaling.

    Parameters
    ----------
    header : dict
        The parsed SDF header information.
    points : np.ndarray
        The raw data points from the SDF file.
    keep_raws : bool, optional
        Whether to keep raw arrays in the output, by default False.
    Returns
    -------
    dict
        Structured arrays and scaling information.
    """

    Nx = int(header["NumPoints"])
    Ny = int(header["NumProfiles"])

    if points.size != Nx * Ny:
        raise ValueError("Binary body size mismatch")

    x_array = np.arange(Nx, dtype=float)
    y_array = np.arange(Ny, dtype=float)
    z_array = points.reshape((Ny, Nx)).astype(float)

    # Axes in physical units
    res = {}

    res["z_array"] = z_array * header["Zscale"]
    res["x_array"] = x_array * header["Xscale"]
    res["y_array"] = y_array * header["Yscale"]
    res["x_offset"] = float(res["x_array"].min())
    res["y_offset"] = float(res["y_array"].min())
    res["z_offset"] = float(res["z_array"].min())

    if keep_raws:
        res["data_unscaled"] = {
            "z_array": z_array,
            "x_array": x_array,
            "y_array": y_array,
        }

    return res


def read_sdf(
    path: Path | str, keep_raws: bool = False, parse_array: bool = True, **kwargs
) -> dict:
    """
    Detect and load an SDF file (ASCII or binary).

    Parameters
    ----------
    path : Path | str
        Path to the SDF file.
    keep_raws : bool, optional
        Whether to keep raw text parts and arrays in the output, by default False.
    parse_array : bool, optional
        Whether to parse and build data arrays, by default True.
    kwargs : dict, optional
        Additional metadata to include in the output.
    Returns
    -------
    dict
        Parsed SDF data and metadata.
    """
    path = Path(path)
    raw = path.read_bytes()
    res = SDF_DEFAULTS.copy()

    if raw.startswith(b"aISO-1.0"):
        res |= read_sdf_ascii(raw)
    elif raw.startswith(b"bISO-1.0"):
        res |= read_sdf_binary(raw)
    else:
        raise ValueError("Unknown SDF signature")

    # Apply scaling to the points in the result
    if parse_array:
        values = res["points"].copy() if keep_raws else res.pop("points")

        res |= _sdf_build_arrays(res, values, keep_raws=keep_raws)

    # --- Metadata ---
    res["filename"] = path.name
    res["path"] = str(path)
    res.setdefault("timestamp", oldest_timestamp(path))

    if not keep_raws:
        res = {SDF_RENAME_MAP.get(k, k): v for k, v in res.items()}
        res |= kwargs
        res = restructure_surf_dict(res)
    else:
        res |= kwargs

    return res


if __name__ == "__main__":
    # Example usage
    gd_folder = Path(
        r"D:\\Online\ASU Dropbox\Jacob Clenney\Work Docs\Data\Analysis\Profilometry\GDOES"
    )

    sdf_1_res = read_sdf(gd_folder / "n15_r12_1_1.sdf")  # "n15_r12_2_1.sdf"

    sdf_2_res = read_sdf(gd_folder / "n15_r12_2_1.sdf")  # "n15_r12_2_1.sdf"

    # sdf_results = {f.stem: read_sdf(f) for f in sdf0_folder.glob("n15_r12_*.sdf")}
