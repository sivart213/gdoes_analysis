from pathlib import Path

import pandas as pd

META_KEYS = ["sig_name", "measurement", "timestamp", "method"]


def parse_jy_file(path: str | Path) -> tuple[dict, pd.DataFrame]:
    header = {}
    data_lines = []
    with open(Path(path), "r", encoding="utf-8") as f:
        lines = [line.strip() for line in f if line.strip()]

    # Split header vs data: header lines don't start with "X"
    for line in lines:
        if line.startswith("X\t") or line[0].isdigit():
            data_lines.append(line)
        else:
            # header lines: first token is the signal name
            parts = line.split("\t", 1)
            if len(parts) == 2:
                signal, meta = parts
                header[signal] = {k: m for k, m in zip(META_KEYS, meta.split(" / "))}
            else:
                header[parts[0]] = ""

    # First line of data_lines is the column header
    col_header = data_lines[0].split("\t")
    # Remaining lines are numeric rows
    rows = [row.split("\t") for row in data_lines[1:]]

    # Build DataFrame
    df = pd.DataFrame(rows, columns=col_header)

    # Convert numeric columns to floats
    df = df.astype(float)

    return header, df


if __name__ == "__main__":
    from pathlib import Path

    file_path = Path(
        r"D:\\Online\ASU Dropbox\Jacob Clenney\Work Docs\Data\Analysis\GDOES\Exported (sudo text files)\n15_25r3_1.jy"
    )
    # from gdoes_analysis.testing import DATA_DIR

    # file_path = DATA_DIR / "202309_conv.jy"
    # file_path = DATA_DIR / "set4A r5_3.jys"

    ref_header, ref_df = parse_jy_file(file_path)
