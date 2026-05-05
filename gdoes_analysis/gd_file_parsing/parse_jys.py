from pathlib import Path

import pandas as pd

from gdoes_analysis.gd_file_parsing.parse_tools import (
    parse_body,
    multi_split,
    group_by_len,
    make_dataframe,
    create_body_dfs,
    multi_partition,
)


# --- Handlers for specific table types ---
def handle_signal_table(df: pd.DataFrame) -> dict[str, pd.DataFrame | pd.Series]:
    df["NOMRAIE"] = pd.to_numeric(df["NOMRAIE"], errors="coerce")
    section_names = df.apply(
        lambda row: (
            row["NOMELEM"]
            if row["NOMRAIE"] == 0
            else f"{row['NOMELEM']} {int(round(row['NOMRAIE']))}"
        ),
        axis=1,
    )
    return {"signal_table": df, "section_names": section_names}


def parse_header(raw: bytes) -> tuple[dict[str, object], bytes]:
    header = {}
    sections, raw = multi_partition(raw, b"\x05", b"\x04")
    header["file_classification"] = sections[0]

    rows: list[list[str]] = multi_split(sections[1], "\r\n", "\t", decode=False)
    groups = group_by_len(rows)

    tables = {}
    for i, group in enumerate(groups):
        df = make_dataframe(*group)

        if "header_table" not in tables:
            tables["header_table"] = df
        elif "NOMELEM" in df.columns and "NOMRAIE" in df.columns:
            tables |= handle_signal_table(df)
        else:
            tables[f"table_{i+1}"] = df

    header.update(tables)
    return header, raw


def main(data: str | Path | bytes, body_sep: bytes = b"\x01\x00\x00\x00") -> tuple[
    dict,
    pd.DataFrame,
    pd.DataFrame,
    dict[str, list[tuple[float, float]]],
    dict[str, bytes],
]:

    if isinstance(data, (str, Path)):
        data = Path(data).read_bytes()

    header, remaining = parse_header(data)

    sections, infos = parse_body(remaining, sep=body_sep)

    df, raw_df = create_body_dfs(sections, infos)

    return header, df, raw_df, sections, infos


if __name__ == "__main__":
    from gdoes_analysis.testing import DATA_DIR

    # file_path = DATA_DIR / "202309.jys"
    file_path = DATA_DIR / "set4A r5_3.jys"

    header, df, raw_df, sections, infos = main(file_path)


# assume raw is the full bytes object read from file
# def parse_header(raw: bytes):
#     header = {}

#     # --- split into 3 main header parts ---
#     file_classification, _, raw = raw.partition(b"\x05")
#     header["file_classification"] = file_classification.decode("utf-8", errors="ignore")

#     second_section, _, raw = raw.partition(b"\x04")
#     # --- split second section into rows ---
#     rows = [
#         r.decode("utf-8", errors="ignore").split("\t") for r in second_section.split(b"\r\n") if r
#     ]

#     groups = []
#     current_group = []
#     current_len = len(rows[0]) if rows else 0
#     for row in rows:
#         if len(row) == current_len:
#             current_group.append(row)
#         else:
#             groups.append(current_group)
#             current_group = [row]
#             current_len = len(row)
#     if current_group:
#         groups.append(current_group)

#     # --- convert groups into DataFrames ---
#     tables = {}
#     # sig_count = 0
#     for i, group in enumerate(groups):

#         df = (
#             pd.DataFrame(group[1:], columns=group[0])
#             if len(group) > 1
#             else pd.DataFrame(columns=group[0])
#         )
#         if "NOMELEM" in df.columns and "NOMRAIE" in df.columns:
#             df["NOMRAIE"] = pd.to_numeric(df["NOMRAIE"], errors="coerce")
#             tables["signal_table"] = df
#             tables["section_names"] = df.apply(
#                 lambda row: (
#                     row["NOMELEM"]
#                     if row["NOMRAIE"] == 0
#                     else f"{row['NOMELEM']} {int(round(row['NOMRAIE']))}"
#                 ),
#                 axis=1,
#             )
#             # sig_count = len(df)
#         elif "header_table" not in tables:
#             tables["header_table"] = df
#         else:
#             tables[f"table_{i+1}"] = df

#     header |= tables

#     return header, raw


# T = TypeVar("T", bound=Sized)


# def recursive_apply(
#     data: Any,
#     recurse_type: type,
#     func: Callable[[Any], Any],
# ) -> Any:
#     if isinstance(data, recurse_type):
#         res = [recursive_apply(d, recurse_type, func) for d in data]
#         return recurse_type(res)
#     else:
#         return func(data)


# @overload
# def multi_partition(
#     raw: bytes, *seps: bytes, decode: Literal[False]
# ) -> tuple[list[bytes], bytes]: ...
# @overload
# def multi_partition(
#     raw: bytes, *seps: bytes, decode: Literal[True] = True
# ) -> tuple[list[str], bytes]: ...


# def multi_partition(
#     raw: bytes, *seps: bytes, decode: bool = True
# ) -> tuple[list[str] | list[bytes], bytes]:
#     """
#     Partition raw bytes sequentially by a list of separators.
#     Returns a list of sections and the remainder. tuple[list[str], bytes] | tuple[list[bytes], bytes]
#     """
#     sections = []
#     resid = raw
#     for sep in seps:
#         part, _, resid = resid.partition(sep)
#         sections.append(part.decode("utf-8", errors="ignore") if decode else part)
#     return sections, resid


# @overload
# def multi_split(
#     section: str,
#     *seps: str | list[str],
#     decode: bool = ...,
#     encoding: str = ...,
#     errors: str = ...,
# ) -> list: ...


# @overload
# def multi_split(
#     section: bytes,
#     *seps: bytes | list[bytes],
#     decode: bool = ...,
#     encoding: str = ...,
#     errors: str = ...,
# ) -> list: ...


# def multi_split(
#     section,
#     *seps,
#     decode=True,
#     encoding="utf-8",
#     errors="ignore",
# ):
#     """
#     Recursively split section by a list of separators.
#     Each separator is applied in order, producing nested lists.
#     Works on str or bytes directly.
#     """
#     if not seps or not section:
#         return (
#             [section.decode(encoding, errors=errors).strip()]
#             if isinstance(section, bytes) and decode
#             else [section]
#         )

#     if isinstance(seps[0], list):
#         for sub_sep in seps[0]:
#             if sub_sep in section:
#                 parts = section.split(sub_sep)
#                 break
#         else:
#             parts = [section]
#     else:
#         parts = section.split(seps[0])

#     if len(seps) == 1:
#         return (
#             [p.decode(encoding, errors=errors).strip() for p in parts if p]
#             if decode and isinstance(section, bytes)
#             else parts
#         )
#     return [
#         multi_split(p, *seps[1:], decode=decode, encoding=encoding, errors=errors)
#         for p in parts
#         if p
#     ]


# def group_by_len(rows: list[T] | tuple[T, ...]) -> list[list[T]]:
#     """Group rows by consistent length."""
#     groups: list[list[T]] = []
#     current_group: list[T] = []
#     current_len = len(rows[0]) if rows else 0
#     for row in rows:
#         if len(row) == current_len:
#             current_group.append(row)
#         else:
#             groups.append(current_group)
#             current_group = [row]
#             current_len = len(row)
#     if current_group:
#         groups.append(current_group)
#     return groups


# def make_dataframe(cols: list[Any], *data: list[Any]) -> pd.DataFrame:
#     """Convert a group of rows into a DataFrame."""
#     return pd.DataFrame(data, columns=cols)
