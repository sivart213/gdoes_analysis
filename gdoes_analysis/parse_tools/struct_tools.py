import re
import string
import struct
import warnings
from typing import Literal, overload

import numpy as np

TOKEN_RE = re.compile(r"([0-9]+|-|\+|\*)?([A-Za-z?])")


EXPANDED_MOD = {
    "-",  # connected length/width
    "+",  # optional single unpack
    "*",  # consume remaining
}

EXPANDED_STR_FMT = {
    "a",  # ASCII string
    "u",  # UTF-8 string
}

EXPANDED_NUM_FMT = {
    "g",  # dynamic float
    "v",  # dynamic signed integer
    "V",  # dynamic unsigned integer
}

EXPANDED_FMT = EXPANDED_STR_FMT | EXPANDED_NUM_FMT

EXPANDED_CHARS = EXPANDED_MOD | EXPANDED_FMT

DYNAMIC_TYPE_MAP = {
    "g": {4: "f", 8: "d"},  # float
    "v": {1: "b", 2: "h", 4: "i", 8: "q"},  # signed integer
    "V": {1: "B", 2: "H", 4: "I", 8: "Q"},  # unsigned integer
}
DYNAMIC_TYPE_MIN = {k: (min(v.keys()), v[min(v.keys())]) for k, v in DYNAMIC_TYPE_MAP.items()}

STRUCT_FMT_FAMILIES = {"g": "fd", "v": "bhilq", "V": "BHILQ"}

STRUCT_FMT_LIMITS = {
    # signed integers
    "b": lambda x: -(2**7) <= x <= 2**7 - 1,
    "h": lambda x: -(2**15) <= x <= 2**15 - 1,
    "i": lambda x: -(2**31) <= x <= 2**31 - 1,
    "l": lambda x: -(2**31) <= x <= 2**31 - 1,
    "q": lambda x: -(2**63) <= x <= 2**63 - 1,
    # unsigned integers
    "B": lambda x: 0 <= x <= 2**8,
    "H": lambda x: 0 <= x <= 2**16,
    "I": lambda x: 0 <= x <= 2**32,
    "L": lambda x: 0 <= x <= 2**32,
    "Q": lambda x: 0 <= x <= 2**64,
    # floats (IEEE‑754)
    "f": lambda x: x == 0 or not np.isfinite(x) or -44.854 <= np.log10(abs(x)) <= 38.532,
    "d": lambda x: x == 0 or not np.isfinite(x) or -323.306 <= np.log10(abs(x)) <= 308.255,
}


STRUCT_CODES = ""
STRUCT_FMT_SIZES = {}
for ch in string.ascii_letters + string.punctuation:
    try:
        size = struct.calcsize(f"<{ch}")
    except struct.error:
        continue

    # Detect collision with extended codes
    if ch in EXPANDED_CHARS:
        raise RuntimeError(
            f"struct has added '{ch}' as a real format code, "
            "which conflicts with the extended codes."
        )

    STRUCT_FMT_SIZES[ch] = size
    STRUCT_CODES += ch


def unpack_num_str(
    data,
    offset=0,
    *,
    endian="<",
    num_fmt="I",
    str_fmt="s",
    others="",
    return_pos=False,
    return_fmt=False,
):
    leng = struct.unpack_from(endian + num_fmt, data, offset)[0]
    out = [leng]
    out.extend(struct.unpack_from(f"{endian}{leng}s{others}", data, offset + 4))

    if str_fmt != "s":
        dec = "ascii" if str_fmt == "a" else "utf-8"
        out[1] = out[1].decode(dec, errors="replace")

    if return_pos:
        out.append(offset + 4 + leng)
        if others:
            out[-1] = out[-1] + struct.calcsize(f"{endian}{others}")

    if return_fmt:
        fmt = f"{endian}{num_fmt}{leng if leng > 1 else ''}s{others}"
        out.append(fmt)

    return out


def dyn_iter_unpack(fmt, data, pos, end=0, return_pos=False):
    """
    Iteratively apply a dynamic-grammar unpack operation over a byte sequence.

    This helper repeatedly invokes :func:`dyn_unpack` using the same dynamic
    format string, advancing the cursor after each successful unpack.  It
    provides a simple mechanism for walking a buffer as long as the format
    sequence can be applied at the current position.

    Unlike the dynamic grammar itself, which supports optional or consuming
    repetition for *single* format tokens (e.g., ``+I``, ``*B``), this function
    repeats the *entire* ``fmt`` sequence as a unit.  It does **not** expand or
    replicate multi-token patterns internally.  For example, if the intended
    repetition is something like ``"<I-a"`` repeated several times, this helper
    can iterate that sequence, but :func:`dyn_unpack` alone cannot express such
    multi-token repetition.

    Parameters
    ----------
    fmt : str
        A dynamic-grammar format string understood by :func:`dyn_unpack`.
        The grammar may include dynamic-length operators (``-``), optional
        tokens (``+``), consuming tokens (``*``), and dynamic-width numeric
        types (``g``, ``v``, ``V``).  The same format sequence is applied on
        each iteration.
    data : bytes-like
        The raw byte buffer to unpack from.
    pos : int
        Starting byte offset within ``data``.
    end : int, optional
        Stopping offset within ``data``.  If ``0`` (default), iteration
        continues until the end of the buffer.
    return_pos : bool, optional
        If ``True``, append the final cursor position to the returned
        ``values`` list.  This mirrors the behavior of ``dyn_unpack`` when
        ``return_pos=True``.

    Returns
    -------
    values : list
        A flat list of all unpacked values produced across iterations.
        If ``return_pos=True``, the final cursor position is appended as
        the last element.
    residual : bytes
        Any remaining bytes between the final cursor and ``end`` (or the
        end of ``data`` if ``end=0``).

    Notes
    -----
    Iteration stops under any of the following conditions:

    * The cursor reaches or exceeds ``end``.
    * :func:`dyn_unpack` raises ``ValueError`` due to insufficient data or
      an invalid token at the current position.
    * The dynamic grammar resolves to zero-length progress (which would
      otherwise risk an infinite loop).

    This helper is intentionally minimal: it does not attempt to infer or
    expand repeated multi-token sequences.  It simply re-applies ``fmt`` as a
    whole, making it suitable for record-like structures where each record
    shares the same dynamic grammar.

    Examples
    --------
    Iterate a simple dynamic record format::

        fmt = "<I-a"   # 4-byte length, followed by ASCII string of that length
        values, residual = dyn_iter_unpack(fmt, data, 0)

    Retrieve the final cursor position::

        values, residual = dyn_iter_unpack(fmt, data, 0, return_pos=True)
        final_pos = values[-1]
    """
    values = []
    cur = pos
    stop = end if end > 0 else len(data)

    while cur < stop:
        try:
            out = dyn_unpack(fmt, data, cur, return_pos=True)
        except ValueError:
            break

        values.extend(out[:-1])
        cur = out[-1]

    if return_pos:
        values.append(cur)

    return values, data[cur:stop]


def round_to_size0(n):
    return 1 << min(3, (n.bit_length() - 1))


def round_to_size(n, max_size=8):
    if not n:
        return 0

    try:
        return 1 << (int(min(max_size, n)).bit_length() - 1)
    except ValueError:
        return 0


def parse_dyn_syntax(
    prefix: str, code: str, space: int, out: list | tuple = tuple(), endian: str = "<"
) -> tuple[str, int, str]:
    """
    Resolves a single dynamic grammar token into a standard struct format code, it's size,
    and optional string decoding type.
    """
    if code in EXPANDED_NUM_FMT:  # DYNAMIC NUMERIC TYPES (v, V, g)
        c_map = DYNAMIC_TYPE_MAP[code]
        c_map_min, c_map_min_fmt = DYNAMIC_TYPE_MIN[code]

        # "-" prefix: connected width
        if prefix == "-":
            width = out[-1] if out else 0
            if width not in c_map:
                raise ValueError("'-' not connected to valid width indicating integer")
            return c_map[width], width, ""

        # "+" prefix: optional single unpack, expand to fit space
        if prefix == "+":
            if space < c_map_min:
                return f"0{c_map_min_fmt}", 0, ""
            width = round_to_size(space)
            return c_map[width], width, ""

        # numeric prefix
        if prefix.isdigit():
            count = int(prefix)
            if count == 0:  # skip entirely
                return f"0{c_map_min_fmt}", 0, ""
        else:
            count = 1

        # ensure enough space
        if c_map_min * count > space:
            return c_map_min_fmt, c_map_min * count, ""

        # greedy width selection
        width = round_to_size(space // count)
        clean_code = c_map[width] if count == 1 else f"{count}{c_map[width]}"
        return clean_code, width * count, ""

    # STATIC PREFIX LOGIC
    if code in EXPANDED_STR_FMT:  # STRING TYPES (a, u)
        root_size = 1
        dec = "ascii" if code == "a" else "utf-8"
        clean_code = "s"
    else:  # STRUCT TYPES
        try:
            root_size = struct.calcsize(f"{endian}{code}")
        except (struct.error, OverflowError) as exc:
            raise ValueError(f"Invalid format code '{code}'") from exc
        dec = ""
        clean_code = code

    if not prefix:  # empty prefix → 1
        return clean_code, root_size, dec

    count = 1
    if prefix.isdigit():  # numeric prefix
        count = int(prefix)
    elif prefix == "-":  # "-" prefix: connected length
        if not out or not isinstance(out[-1], int):
            raise ValueError("'-' not connected to valid integer")
        count = out[-1]
    elif prefix == "+":  # "+" prefix: optional single unpack
        count = int(space >= root_size)

    if count == 1:
        return clean_code, root_size, dec
    return f"{count}{clean_code}", root_size * count, dec


def dyn_unpack(
    fmt: str,
    data: bytes,
    offset: int = 0,
    *,
    errors: str = "raise",
    return_pos: bool = False,
    return_fmt: bool = False,
) -> list:
    """
    Extended binary unpacking using ``struct.unpack_from`` with prefix operators,
    dynamic-width integer/float types, and lightweight string decoding.

    Parameters
    ----------
    fmt : str
        A format string consisting of an optional endian prefix
        ('<', '>', '=', '!', '@') followed by a sequence of tokens.
        Each token has the form::

            PREFIX? CODE

        where ``PREFIX`` modifies the behavior of ``CODE`` according to the
        extended grammar described below.

    data : bytes-like
        The byte buffer to unpack from.

    offset : int, optional
        Starting byte offset into ``data``. Default is 0.

    errors : {"raise", "warn"/"warning", "ignore"}, optional
        Error-handling behavior for struct unpack failures.

        - "raise"  : raise a ValueError on failure.
        - "warn"   : emit a warning and stop unpacking.
        - "ignore" : silently stop unpacking.

    return_pos : bool, optional
        Whether to append the final byte offset after unpacking.
        If True, the offset will always be directly after the last
        successfully unpacked token. Default is False.

    return_fmt : bool, optional
        Whether to append the reconstructed struct format string used during
        unpacking. If True, the format string is appended as the final item
        (or after ``return_pos`` if both are enabled). Default is False.

    Returns
    -------
    out : list
        A list of unpacked values. For string-like codes (``s``, ``a``, ``u``),
        the returned value is either a decoded string (ASCII or UTF‑8) or a
        raw bytes object.

        If ``return_pos`` is True, the final byte offset is appended.

        If ``return_fmt`` is True, the fully resolved struct format string is
        appended.

    Notes
    -----
    This function extends Python's ``struct`` format syntax with:

    - three prefix operators (``N``, ``-``, ``+``, ``*``)
    - two string-decoding codes (``a``, ``u``)
    - three dynamic-width numeric types (``v``, ``V``, ``g``)

    All unpacking is strictly sequential: each token consumes bytes from the
    current position and advances the offset.

    Extended Grammar
    ----------------
    Each token has the form::

        PREFIX? CODE

    **CODE** (base type)
        - ``s`` : raw bytes (struct semantics)
        - ``a`` : ASCII-decoded string (maps to ``s`` internally)
        - ``u`` : UTF‑8–decoded string (maps to ``s`` internally)
        - ``v`` : dynamic-width *signed* integer
        - ``V`` : dynamic-width *unsigned* integer
        - ``g`` : dynamic-width float (4 or 8 bytes)
        - any other struct-compatible code (e.g., ``b``, ``h``, ``I``, ``f``)

        Dynamic-width codes (``v``, ``V``, ``g``) resolve to a concrete struct
        code based on the available buffer space and the prefix length. The
        resolved code is always one of the standard struct types (e.g. ``B``,
        ``H``, ``I``, ``Q``, ``f``, ``d``).

    **PREFIX** (optional)
        - ``N`` (digits)
            Explicit repeat count. ``"4h"`` unpacks four ``h`` values.

        - ``-`` (connected length/width)
            Use the *immediately preceding output value* to parameterize the
            subsequent token. The previous output must be an integer.

            - For fixed‑width types (including ``s``), the value becomes the
            repeat count.

            - For dynamic‑width types (``v``, ``V``, ``g``), the value becomes
            the byte‑width of the type. The width must be one of the valid
            sizes for that dynamic type (e.g., {1,2,4,8} for ``v``/``V``,
            {4,8} for ``g``). The token then unpacks exactly one value of
            that resolved width.

            Examples::

                "<I-s"     → unpack I, then unpack s of length equal to that I
                "<b-i"     → unpack b, then unpack i repeated b times
                "<b-g"     → unpack b, convert g to f if b==4 else d if b==8 else error
                "<f-i"     → error: previous output not integer
                "<-i"      → error: no previous output


        - ``-`` (connected length/width)
            Use the *immediately preceding output value* to parameterize the
            subsequent token.

            - For fixed-width types (including ``s``), the value becomes the
            repeat count. Example::

                "I-s"   → unpack I, then unpack s of length equal to that I.
                "b-i"   → unpack b, then unpack i repeated b times.

            - For dynamic-width types (``v``, ``V``, ``g``), the value determines
            the byte-width of the type (clamped to a maximum of 8). The token
            then unpacks exactly one value of that resolved width.

            The previous output must be an integer; otherwise a ValueError is raised.

        - ``+`` (optional single unpack)
            Attempt to unpack exactly one instance of the resolved base type.
            If insufficient bytes remain, the token is skipped.
            ``+`` tokens must form a contiguous block at the end of the format.

        - ``*`` (consume remaining)
            Consume as many base units as fit in the remaining buffer.
            ``*`` may only appear on the final token.

        - (empty)
            Equivalent to ``"1"`` — unpack exactly one instance.

    Dynamic-Width Types
    -------------------
    Codes ``v``, ``V``, and ``g`` are designed to work with the ``-`` prefix,
    which explicitly supplies their byte-width. When no width is provided,
    these types fall back to *greedy* selection: they choose the largest or
    smallest valid width depending on the prefix constraints. Use with ``+``
    and ``*`` is supported but not recommended, as their greedy logic may
    select widths that differ from the intended fixed-size interpretation.

    Width selection depends on the prefix:

    - ``-`` (connected width)
        Use the immediately preceding integer output as the width. The value
        must be one of the valid widths for that dynamic type.

    - Numeric prefixes (``N``)
        Choose the largest width such that ``N * width`` fits in the remaining
        buffer.

    - ``+`` (optional single unpack)
        Choose a width that allows at least one element: largest if it fits,
        otherwise smallest.

    - ``*`` (consume remaining)
        Choose a width that yields more than one element when possible:
        largest if it produces multiple items, otherwise smallest.

    If no valid width fits, a ValueError is raised.

    String Decoding
    ---------------
    Codes ``a`` and ``u`` are syntactic sugar for ``s`` with automatic
    decoding:

        - ``a`` → decode as ASCII (errors="replace")
        - ``u`` → decode as UTF‑8 (errors="replace")

    The underlying struct format always uses ``s`` with the computed length.


    Error Handling
    --------------
    Struct unpack failures are handled according to the ``errors`` parameter,
    allowing partial decoding of data streams for exploratory or diagnostic
    purposes. Grammar violations in the extended format syntax (e.g., misplaced
    ``*`` or ``+``) always raise immediate ValueError exceptions and are not
    affected by the ``errors`` setting.

    Examples
    --------
    Basic unpacking
    ^^^^^^^^^^^^^^^
    >>> dyn_unpack("<2hI", b"\\x01\\x00\\x02\\x00\\x05\\x00\\x00\\x00")
    [1, 2, 5]

    Connected-length string
    ^^^^^^^^^^^^^^^^^^^^^^^
    >>> dyn_unpack("<I-s", b"\\x05\\x00\\x00\\x00hello")
    [5, 'hello']

    Optional unpack (+)
    ^^^^^^^^^^^^^^^^^^^
    If the buffer is too short for the optional field, it is skipped:

    >>> dyn_unpack("<h+i", b"\\x01\\x00")   # only 'h' fits
    [1]

    Consume remaining (*)
    ^^^^^^^^^^^^^^^^^^^^^
    >>> dyn_unpack("<B*H", b"\\x02\\x01\\x00\\x02\\x00")
    [2, 1, 2]

    Returning final offset
    ^^^^^^^^^^^^^^^^^^^^^^
    >>> dyn_unpack("<2h", b"\\x01\\x00\\x02\\x00", return_pos=True)
    [1, 2, 4]

    Returning reconstructed struct format
    ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
    >>> dyn_unpack("<I-s", b"\\x05\\x00\\x00\\x00hello", return_fmt=True)
    ['hello', '<i5s']

    Combining both return flags
    ^^^^^^^^^^^^^^^^^^^^^^^^^^^
    >>> dyn_unpack("<I-s", b"\\x05\\x00\\x00\\x00hello", return_pos=True, return_fmt=True)
    ['hello', 9, '<i5s']

    Ignoring length errors
    ^^^^^^^^^^^^^^^^^^^^^^
    If the buffer ends early, only length-related errors may be ignored:

    >>> dyn_unpack("<2hI", b"\\x01\\x00\\x02\\x00", errors="ignore")
    [1, 2]

    Warning on length errors
    ^^^^^^^^^^^^^^^^^^^^^^^^
    >>> dyn_unpack("<I-s", b"\\x05\\x00\\x00\\x00he", errors="warn")
    __main__:1: UserWarning: Error unpacking token '<5s' ('-s') at pos 4: unpack_from requires a buffer of at least 9 bytes for unpacking 5 bytes at offset 4 (actual buffer size is 6)
    [ ]

    Hard failure for non-length errors
    ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
    Invalid format syntax always raises immediately, regardless of ``errors``:

    >>> dyn_unpack("<h+2i", b"\\x01\\x00\\x02\\x00\\x03\\x00")
    Traceback (most recent call last):
        ...
    ValueError: '+' may only appear towards the end of the format string
    """

    if EXPANDED_CHARS.isdisjoint(set(fmt)):
        try:
            out = list(struct.unpack_from(fmt, data, offset))
            if return_pos:
                out.append(offset + struct.calcsize(fmt))
            if return_fmt:
                out.append(fmt)
            return out
        except (struct.error, OverflowError) as exc:
            raise ValueError(
                f"Error unpacking format '{fmt}' directly at offset {offset}"
            ) from exc

    out = []
    pos = max(0, offset)
    n_data = len(data)

    fmt = fmt.strip().replace(" ", "")

    if not fmt:
        if return_pos:
            out.append(pos)
        if return_fmt:
            out.append("")
        return out

    # endian, body = split_endian(fmt)
    endian, body = (fmt[0], fmt[1:]) if fmt[0] in "<>=!@" else ("<", fmt)

    repeated = ""
    if "*" in body:
        if body.count("*") > 1:
            raise ValueError("'*' may only appear once in the format string")
        body, repeated = body.split("*")
        if "+" in repeated:
            raise ValueError(
                "'+' not allowed after '*'.  Optional unpacking within the consume block is not supported."
            )
        if not repeated:
            warnings.warn("'*' with no following fmt code is ignored")

    tokens = TOKEN_RE.findall(body)

    if "+" in body:
        first_plus = next((i for i, (p, _) in enumerate(tokens) if p == "+"), -1)
        if first_plus >= 0 and any(p != "+" for p, _ in tokens[first_plus:]):
            raise ValueError("'+' may only appear towards the end of the format string")

    rev_fmt = endian
    # for prefix, code in zip(prefixes, fmts):
    for prefix, code in tokens:
        if prefix in EXPANDED_MOD or code in EXPANDED_FMT:
            space = n_data - pos
            try:
                clean_code, size, decode_type = parse_dyn_syntax(
                    prefix or "1", code, space, out, endian=endian
                )
            except ValueError:
                raise

            if not size:
                continue

            try:
                raw = struct.unpack_from(f"{endian}{clean_code}", data, pos)
            except (struct.error, OverflowError) as exc:
                msg = (
                    f"Error unpacking token '{endian}{clean_code}' ('{prefix}{code}') at pos {pos}"
                )
                # Detect non length-related errors
                if "requires a buffer of at least" not in str(exc):
                    # This is a real struct error (bad format, invalid code, etc.)
                    raise ValueError(msg) from exc

                if errors.lower().startswith("warn"):
                    warnings.warn(msg + f": {exc}")
                    break
                elif errors.lower() == "ignore":
                    break
                else:
                    raise ValueError(msg) from exc

            if decode_type:
                out.append(raw[0].decode(decode_type, errors="replace"))
            else:
                out.extend(raw)

            rev_fmt += clean_code
            pos += size

        else:
            # If prefix is not in EXPANDED_MOD and code is not in EXPANDED_FMT, treat as normal
            try:
                fmt = endian + prefix + code
                out.extend(struct.unpack_from(fmt, data, pos))

                rev_fmt += fmt[1:]
                pos += struct.calcsize(fmt)
            except (struct.error, OverflowError) as exc:
                raise ValueError(
                    f"Error unpacking token '{endian}{prefix}{code}' directly at pos {pos}"
                ) from exc

    if repeated:
        rep_fmt = endian + repeated
        if EXPANDED_CHARS.isdisjoint(set(repeated)):
            root_size = struct.calcsize(rep_fmt)
            length = (n_data - pos) // root_size
            out.extend(struct.unpack_from(f"{endian}{length}{repeated}", data, pos))
            pos += root_size * length
            rev_fmt += f"{length}{repeated}"

        else:
            while pos < n_data:
                try:
                    out_extra = dyn_unpack(
                        repeated,
                        data,
                        pos,
                        errors="ignore",
                        return_pos=True,
                        return_fmt=True,
                    )
                except ValueError as exc:
                    raise ValueError(
                        f"Error unpacking repeated token '{endian}{repeated}' at pos {pos}"
                    ) from exc

                out.extend(out_extra[:-2])
                pos = out_extra[-2]
                rev_fmt += out_extra[-1][1:]  # skip endian

    if return_pos:
        out.append(pos)
    if return_fmt:
        out.append(rev_fmt)
    return out


@overload
def dyn_pack_str(
    fmt: str,
    value: str | bytes,
    *,
    encoding: str = ...,
    return_fmt: Literal[True],
) -> tuple[bytes, str]: ...


@overload
def dyn_pack_str(
    fmt: str,
    value: str | bytes,
    *,
    encoding: str = ...,
    return_fmt: Literal[False] = False,
) -> bytes: ...


def dyn_pack_str(
    fmt: str,
    value: str | bytes,
    *,
    encoding: str = "utf-8",
    return_fmt: bool = False,
) -> bytes | tuple[bytes, str]:
    """
    Pack a single string or byte string using an optional length prefix,
    returning the exact struct format used if requested.

    Parameters
    ----------
    fmt : str
        A format string of the form::

            ENDIAN? INT_CODE? STRING_CODE

        Examples:
            "<Is", "<Iu", ">Hs", "<s", "u"

        If INT_CODE is provided, the output will be length‑prefixed using
        that integer type. If INT_CODE is omitted, no length prefix is
        included and only the encoded bytes are packed.

        The STRING_CODE must be one of: 's', 'a', 'u'.

        A '-' prefix before the string code is allowed but ignored.
        For example, "<I-s" is treated the same as "<Is".


    value : str or bytes
        The string or byte string to encode.

    encoding : str, optional
        Encoding to use when STRING_CODE is 'u' or when STRING_CODE is 's'
        and `value` is a Python string. Default is "utf-8".

    return_fmt : bool, optional
        Whether to return the reconstructed struct format string
        alongside the packed bytes.

    Returns
    -------
    packed : bytes
        The packed binary representation.

    (packed, fmt_out) : tuple, optional
        If `return_fmt` is True, also return the canonical struct format
        string used for packing.

    Notes
    -----
    This function is intentionally limited to a single length-prefixed
    string. It does not support repetition, optional prefixes, or the
    full extended grammar used by `dyn_unpack`.

    If no integer code is provided and `return_fmt` is False, this function
    is equivalent to calling `value.encode(...)` which should be used instead.
    Doing so avoids unnecessary parsing overhead.

    """

    if not fmt:
        raise ValueError("Format string cannot be empty")

    # --- Parse endian ---
    endian, body = (fmt[0], fmt[1:]) if fmt[0] in "<>=!@" else ("<", fmt)

    # --- Remove optional '-' prefix ---
    body = body.replace("-", "").replace(" ", "")

    # --- Determine codes ---
    if len(body) == 1:
        # Only string code provided → use default integer type
        int_code = ""
        str_code = body
    elif len(body) == 2:
        int_code, str_code = body
    else:
        raise ValueError("Format must contain one or two codes (int?, string)")

    # --- Encode the value ---
    if isinstance(value, str):
        if str_code == "a":
            encoded = value.encode("ascii", errors="replace")
        else:
            encoded = value.encode(encoding)
    else:
        encoded = value

    length = len(encoded)

    # --- Validate string code ---
    if str_code not in ("s", "a", "u"):
        raise ValueError("Second code must be one of: 's', 'a', 'u'")

    # --- Validate number/pack basic ---
    fmt_out = f"{endian}{length}s"
    try:
        packed = struct.pack(fmt_out, encoded)
    except (struct.error, OverflowError) as exc:
        raise ValueError(f"Error packing {encoded} as '{fmt_out}'") from exc

    if int_code:
        # --- Validate integer code ---
        prefix = endian + int_code
        try:
            int_bytes = struct.pack(prefix, length)
            unp_len = struct.unpack(prefix, int_bytes)[0]
        except (struct.error, OverflowError) as exc:
            raise ValueError(f"Invalid integer code '{int_code}' for length {length}") from exc

        if unp_len != length or not isinstance(unp_len, int):
            raise ValueError(f"Integer code '{int_code}' does not correctly store length {length}")

        fmt_out = f"{prefix}{length}s"
        packed = int_bytes + packed
    # else:
    #     fmt_out = f"{endian}{length}s"
    #     packed = struct.pack(fmt_out, encoded)

    return (packed, fmt_out) if return_fmt else packed


@overload
def dyn_pack_num(
    fmt: str,
    value: int | float,
    *,
    return_fmt: Literal[True],
) -> tuple[bytes, str]: ...


@overload
def dyn_pack_num(
    fmt: str,
    value: int | float,
    *,
    return_fmt: Literal[False] = False,
) -> bytes: ...


def dyn_pack_num(
    fmt: str,
    value: int | float,
    *,
    return_fmt: bool = False,
) -> bytes | tuple[bytes, str]:
    """
    Pack a single numeric value using an optional integer prefix and
    supporting dynamic-width types ('v', 'V', 'g').

    Parameters
    ----------
    fmt : str
        A format string of the form::

            ENDIAN? INT_CODE? NUM_CODE

        Examples:
            "<Iv", "<Hg", ">v", "V", "g"

        If INT_CODE is provided, the output will be length‑prefixed using
        that integer type. If INT_CODE is omitted, only the numeric value
        is packed.

        NUM_CODE may be any struct-compatible numeric code, including the
        dynamic-width types:
            - 'v' : signed integer (1, 2, 4, or 8 bytes)
            - 'V' : unsigned integer (1, 2, 4, or 8 bytes)
            - 'g' : float (4 or 8 bytes)

        A '-' prefix before the numeric code is allowed but ignored.

    value : int or float
        The numeric value to pack.

    return_fmt : bool, optional
        Whether to return the canonical struct format string used for
        packing. Default is False.

    Returns
    -------
    packed : bytes
        The packed binary representation.

    (packed, fmt_out) : tuple, optional
        If `return_fmt` is True, also return the canonical struct format
        string used for packing.
    """

    if not fmt:
        raise ValueError("Format string cannot be empty")

    # --- Parse endian ---
    endian, body = (fmt[0], fmt[1:]) if fmt[0] in "<>=!@" else ("<", fmt)

    # --- Remove optional '-' prefix ---
    body = body.replace("-", "").replace(" ", "")

    # --- Determine codes ---
    if len(body) == 1:
        int_code = ""
        num_code = body
    elif len(body) == 2:
        int_code, num_code = body
    else:
        raise ValueError("Format must contain one or two codes (int?, number)")

    # --- Resolve/validate num_code to valid struct format ---
    if num_code in {"v", "V", "g"}:
        number = float(value) if num_code == "g" else int(value)
        # Try smallest → largest
        for num_code in STRUCT_FMT_FAMILIES[num_code]:
            if STRUCT_FMT_LIMITS[num_code](number):
                break

    elif num_code in STRUCT_FMT_FAMILIES["g"]:
        number = float(value)
    else:
        number = int(value)

    # --- Validate num_code/get size ---
    try:
        size = struct.calcsize(endian + num_code)
    except (struct.error, OverflowError) as exc:
        raise ValueError(f"Invalid numeric code '{num_code}'") from exc

    # --- Validate number/pack basic ---
    fmt_out = f"{endian}{num_code}"
    try:
        packed = struct.pack(fmt_out, number)
    except (struct.error, OverflowError):
        raise ValueError(f"Value '{value}' out of range for format '{num_code}'")

    if int_code:
        # --- Validate integer code ---
        prefix = endian + int_code
        try:
            int_bytes = struct.pack(prefix, size)
            unp_size = struct.unpack(prefix, int_bytes)[0]
        except (struct.error, OverflowError) as exc:
            raise ValueError(f"Invalid integer code '{int_code}' for width {size}") from exc

        if unp_size != size or not isinstance(unp_size, int):
            raise ValueError(f"Integer code '{int_code}' does not correctly store width {size}")

        fmt_out = f"{prefix}{num_code}"
        packed = int_bytes + packed

    return (packed, fmt_out) if return_fmt else packed


# first_plus = next((i for i, p in enumerate(prefixes) if p == "+"), -1)
# if any(p not in ("+", "*") for p in prefixes[first_plus:]):
# if any(p not in ("+", "*") for p in prefixes[prefixes.index("+") :]):
# non_tokens = [p[0] not in END_ONLY_MODS for p in tokens]
# if any(non_tokens[non_tokens.index(False):]):


# def _unpack_code_parse(prefix, code, space, out, endian="<"):
#     """
#     Parse a single format code (including dynamic types and a/u decoding)
#     but do NOT finalize prefix/length logic.
#     """
#     if code in EXPANDED_NUM_FMT:
#         c_map = DYNAMIC_TYPE_MAP[code]

#         if prefix == "-":
#             # must be connected to a valid byte width format
#             if not out or out[-1] not in c_map:
#                 raise ValueError("'-' not connected to valid width indicating integer")

#             return c_map[out[-1]], "", out[-1]

#         c_map_min = DYNAMIC_TYPE_MIN[code]
#         if prefix == "+":
#             root_size = round_to_size(max(c_map_min, space))
#             return c_map[root_size], "", root_size * int(space >= root_size)

#         if prefix.isdigit():
#             count = int(prefix)
#             if count == 0:
#                 # code size no longer matters
#                 return f"0{c_map[c_map_min]}", "", 0

#         else:  # empty prefix ("") -> 1
#             count = 1
#             prefix = "1"

#         if c_map_min * count > space:
#             # ensures space // count >= c_map_min & not 0
#             raise ValueError(
#                 f"Insufficient data: dynamic type '{code}' with count {count} "
#                 f"requires a buffer of at least {c_map_min * count} bytes "
#                 f"(available buffer size is {space})"
#             )
#         root_size = round_to_size(space // count)
#         new_code = c_map[root_size] if count == 1 else f"{count}{c_map[root_size]}"
#         return new_code, "", root_size * count

#     if code in EXPANDED_STR_FMT:
#         dec = "ascii" if code == "a" else "utf-8"
#         code = "s"
#         root_size = 1
#         # return "s", dec, prefix, 1
#     else:
#         dec = ""
#         try:
#             root_size = struct.calcsize(f"{endian}{code}")
#         except (struct.error, OverflowError) as exc:
#             raise ValueError(f"Invalid format code '{code}'") from exc

#     if not prefix:
#         return code, dec, root_size
#     elif prefix.isdigit():
#         new_code = f"{prefix}{code}" if int(prefix) > 1 else code
#         return new_code, dec, root_size * int(prefix)
#     elif prefix == "-":  # use connected integer as length
#         if not out or not isinstance(out[-1], int):
#             raise ValueError("'-' not connected to valid integer")
#         new_code = f"{out[-1]}{code}" if out[-1] > 1 else code
#         return new_code, dec, root_size * out[-1]
#     elif prefix == "+":  # optional unpack
#         return code, dec, root_size * int(space >= root_size)  # skip this token entirely

#     return code, dec, root_size
