import string
import struct

import pytest

from testing.helpers import set_section, buffered_print
from gdoes_analysis.testing.helpers import print_test_result
from gdoes_analysis.parse_tools.struct_tools import (
    DYNAMIC_TYPE_MAP,
    STRUCT_FMT_SIZES,
    dyn_unpack,
    dyn_pack_num,
    dyn_pack_str,
    parse_dyn_syntax,
)

NUM_FMT_CODES = [
    c for ch in string.ascii_lowercase for c in (ch, ch.upper()) if c in DYNAMIC_TYPE_MAP
]

STRING_CODES = {"a": ("s", "ascii"), "u": ("s", "utf-8")}
DYNAMIC_TYPE_MIN_WIDTH = {k: min(v.keys()) for k, v in DYNAMIC_TYPE_MAP.items()}
DYNAMIC_TYPE_MIN_FMT = {k: v[min(v.keys())] for k, v in DYNAMIC_TYPE_MAP.items()}


# ------------------------------------------------------------
set_section("Tests for parse_dyn_syntax")
# ------------------------------------------------------------


# ----- Error cases -----
@pytest.mark.parametrize(
    "prefix, code, out, space, description",
    [
        ("", "ZZ", [], 64, "invalid static code"),
        ("-", "B", [], 64, "minus prefix without integer"),
        ("-", "B", [1.0], 64, "minus prefix non-integer"),
        ("-", "g", [3], 64, "invalid integer width for float"),
        ("-", "v", [3], 64, "invalid integer width for signed int"),
        ("-", "V", [3], 64, "invalid integer width for unsigned int"),
    ],
)
def test_parse_dyn_syntax_errors(prefix, code, out, space, description):
    with pytest.raises(ValueError) as excinfo:
        parse_dyn_syntax(prefix, code, space, out)
    print_test_result(description, error=excinfo)


def test_parse_dyn_syntax_static_base(subtests):
    fmt_sizes = STRUCT_FMT_SIZES | {k: 1 for k in "au"}
    for code, base in fmt_sizes.items():
        ret_code, dec_base = STRING_CODES.get(code, (code, ""))
        with subtests.test(msg="Test w/ all prefixes (standard and expanded)", code=code):
            for pre in ["+", "-", ""]:
                for count in range(1, 4):
                    prefix = pre or str(count)
                    # ret_size = (min(count, 1) * base) if pre == "+" else (count * base)
                    ret_size = base if pre == "+" else (count * base)

                    fmt, size, dec = parse_dyn_syntax(prefix, code, count * base, [count])
                    assert fmt[-1] == ret_code
                    assert size == ret_size
                    assert dec == dec_base
                    if pre != "+" and count > 1:
                        # For non-optional codes, size should scale with count
                        assert fmt[0] == str(
                            count
                        ), f"Expected count prefix in fmt for {prefix}{code}"


# ----- Edge cases -----
def test_parse_dyn_syntax_0_fmts(subtests):
    # --- Group 1: static struct codes ---
    for pre in ("0", "+"):
        with subtests.test(msg="test zero-case struct codes", prefix=pre):
            for code in STRUCT_FMT_SIZES.keys():
                fmt, size, _ = parse_dyn_syntax(pre, code, space=0, out=[])
                assert fmt == f"0{code}"
                assert size == 0

        # --- Group 2: string codes ---
        with subtests.test(msg="test zero-case string codes", prefix=pre):
            for code, (exp_fmt, exp_dec) in STRING_CODES.items():
                fmt, size, dec = parse_dyn_syntax(pre, code, space=0, out=[])
                assert fmt == f"0{exp_fmt}"
                assert size == 0
                assert dec == exp_dec

        # --- Group 3: dynamic numeric codes ---
        with subtests.test(msg="test zero-case numeric codes", prefix=pre):
            for code in NUM_FMT_CODES:
                exp = DYNAMIC_TYPE_MIN_FMT[code]
                fmt, size, _ = parse_dyn_syntax(pre, code, space=0, out=[])
                assert fmt == f"0{exp}"
                assert size == 0


def test_parse_dyn_syntax_numeric_base(subtests):
    for code in NUM_FMT_CODES:
        type_map = DYNAMIC_TYPE_MAP[code]
        min_w = DYNAMIC_TYPE_MIN_WIDTH[code]

        # Build groups: expected_fmt → list of (space, prefixes)
        groups = {v: [] for v in type_map.values()}
        width = min_w
        expected_fmt = type_map[min_w]
        for space in range(min_w, 10):
            # Determine expected_fmt and valid prefixes for this space
            prefixes = ("+", "")
            if space in type_map:
                expected_fmt = type_map[space]
                width = space
                prefixes = ("-", "+", "")

            groups[expected_fmt].append((space, width, prefixes))

        # Now run one subtest per expected_fmt
        for expected_fmt, entries in groups.items():
            with subtests.test(
                msg=f"numeric-base {code}: expect fmt='{expected_fmt}'",
            ):
                for space, width, prefixes in entries:
                    for prefix in prefixes:
                        fmt, size, _ = parse_dyn_syntax(prefix, code, space=space, out=[space])
                        assert fmt == expected_fmt
                        assert size == width


def test_parse_dyn_syntax_numeric_greedy(subtests):
    for code in NUM_FMT_CODES:
        type_map = DYNAMIC_TYPE_MAP[code]
        fmts = set(type_map.values())
        widths = sorted(type_map.keys())
        next_widths = widths[1:] + [widths[-1]]  # for greedy check

        max_w = max(type_map.keys())
        min_w = DYNAMIC_TYPE_MIN_WIDTH[code]
        min_fmt = DYNAMIC_TYPE_MIN_FMT[code]

        for count in range(1, 5):
            min_space = min_w * count - 1
            max_space = max_w * (count + 1)
            res_fmts = set()
            failures = []

            # --- Phase 1: compact subtest ---
            with subtests.test(
                msg=f"greedy numeric behavior for {count}{code}",
                min_space=min_space,
                max_space=max_space,
            ):
                for space in range(min_space, max_space + 1):
                    try:
                        fmt, size, _ = parse_dyn_syntax(str(count), code, space=space, out=[])

                        assert size % count == 0, "size not divisible by count"
                        width = size // count

                        if space > max_w * count:
                            assert width == max_w, "width should be max due to extra space"

                        elif space < min_w * count:
                            assert width == min_w, "width should be min due to insufficient space"
                            assert fmt[-1] == min_fmt, "wrong fmt for min width"

                        elif space == max_w * count:
                            assert width == max_w, "width should be max at exact fit"
                            res_fmts.add(fmt[-1])

                        else:
                            next_size = next_widths[widths.index(width)] * count
                            assert next_size > space, "width not greedy"
                            res_fmts.add(fmt[-1])

                    except AssertionError as exc:
                        failures.append((space, exc))

                # If no failures, finish normally
                if not failures and count:
                    assert res_fmts == fmts, f"Did not produce all formats for {count}{code}"
                    continue

            # --- Phase 2: detailed subtests for each failing space ---
            for space, err in failures:
                with subtests.test(
                    msg=f"failure detail for {count}{code} at space={space}",
                    space=space,
                ):
                    raise err


# ------------------------------------------------------------
set_section("Tests for dyn_unpack")
# ------------------------------------------------------------

CANON = (
    b"\x05"  # 0: length=5
    b"hello"  # 1-5: ascii string
    b"\x03"  # 6: length=3
    b"\xe2\x98\x83"  # 7-9: utf8 snowman (3 bytes)
    b"\x01"  # 10: width=1
    b"\x7f"  # 11: signed int 1-byte
    b"\x02"  # 12: width=2
    b"\x01\x02"  # 13-14: unsigned int 2-byte
    b"\x04"  # 15: width=4
    b"\x00\x00\x80?"  # 16-19: float32 = 1.0
    b"\x08"  # 20: width=8
    b"\x00\x00\x00\x00\x00\x00\xf0?"  # 21-28: float64 = 1.0
    b"\xaa\xbb\xcc\xdd\xee\xff"  # 29-34: trailing bytes for * and +
)


# ----- Error handling -----
@pytest.mark.parametrize(
    "fmt, offset, endpoint, expect, description",
    [
        # 1) Pure struct error
        ("<Bz", 0, None, "error", "invalid code in root-level struct unpack"),
        # 2) More than one '*'
        ("<B*H*B", 0, None, "error", "multiple '*' tokens not allowed"),
        # 3) '+' after '*'
        ("<B*H+B", 0, None, "error", "'+' after '*' not allowed"),
        # 4) '*' with no following fmt → warning
        ("<B-s*", 0, None, "warning", "warning for '*' with no following fmt code"),
        # 5) Numeric prefix after '+'
        ("<B+H2B", 0, None, "error", "numeric prefix after '+' block"),
        # 6) Invalid type with expanded prefix
        ("B-z", 0, None, "error", "invalid code sent to parse_dyn_syntax"),
        # 8) Invalid type with no expanded syntax
        ("<B2z", 0, None, "error", "invalid code in loop-level struct unpack"),
        # 9) length error inside repeated-section loop
        ("<B*B-z", 0, 7, "error", "syntax error after '*' should be raised"),
        ("<B*B-s", 0, 7, "pass", "length error after '*' should be ignored"),
    ],
)
def test_dyn_unpack_errors_base(fmt, offset, endpoint, expect, description, subtests):
    data = CANON[:endpoint]

    # Test both error modes: "raise" and "ignore"
    for mode in ("raise", "ignore"):
        with subtests.test(errors=mode):
            if expect == "warning":
                with pytest.warns(UserWarning) as record:
                    dyn_unpack(fmt, data, offset=offset, errors=mode)
                print_test_result(
                    f"{description} [mode={mode}]",
                    warnings=record,
                )

            elif expect == "error":
                with pytest.raises(ValueError) as excinfo:
                    dyn_unpack(fmt, data, offset=offset, errors=mode)
                print_test_result(
                    f"{description} [mode={mode}]",
                    error=excinfo,
                )
            else:  # expect == "pass"
                out = dyn_unpack(fmt, data, offset=offset, errors=mode)
                assert isinstance(out, list)
                print_test_result(f"{description} [mode={mode}]")


def test_dyn_unpack_errors_length(subtests, override_parse_output):
    override_parse_output("5s")
    for errors in ("raise", "warn", "ignore"):
        with subtests.test(
            msg="length error controlled by errors. Unpacking '5s' w/ space of 2", errors=errors
        ):
            buffered_print(
                f"Testing loop err w/ sub fmt=5s (full fmt='<B-a') on buffer: {CANON[:3]}"
            )

            if errors == "warn":
                with pytest.warns(UserWarning) as record:
                    dyn_unpack("<B-a", CANON[:3], offset=0, errors=errors)
                print_test_result(f"length error [mode={errors}]", warnings=record)

            elif errors == "raise":
                with pytest.raises(ValueError) as excinfo:
                    dyn_unpack("<B-a", CANON[:3], offset=0, errors=errors)
                print_test_result(f"length error [mode={errors}]", error=excinfo)

            else:  # errors == "ignore"
                out = dyn_unpack("<B-a", CANON[:3], offset=0, errors=errors)
                assert isinstance(out, list)
                print_test_result(f"length error [mode={errors}]")

    override_parse_output("-a")
    for errors in ("raise", "warn", "ignore"):
        with subtests.test(
            msg="syntax error ignored by errors. Unpacking '-a' w/ valid space", errors=errors
        ):
            buffered_print(
                f"Testing loop err w/ sub fmt=-a (full fmt='<B-a') on buffer: {CANON[:10]}"
            )

            with pytest.raises(ValueError) as excinfo:
                dyn_unpack("<B-a", CANON, offset=0, errors=errors)

            print_test_result(f"syntax error [mode={errors}]", error=excinfo)


# ----- Test other input args: offset, return_pos, return_fmt -----
def test_dyn_unpack_args():
    out = dyn_unpack("<B-a", CANON, return_pos=True, return_fmt=True)
    assert out == [5, "hello", 6, "<B5s"]
    out = dyn_unpack("<B-u", CANON, offset=6, return_pos=True, return_fmt=True)
    assert out == [3, "☃", 10, "<B3s"]


# ----- Test behavior of various dynamic unpacking features -----
@pytest.mark.parametrize(
    "fmt, offset, endpoint, expected, description",
    [
        # Connected-length strings
        # B=5, then -s uses 5 → b"hello"
        ("<B-s", 0, None, [5, b"hello"], "connected ascii string (raw bytes via -s)"),
        # B=5, then -a uses 5 → "hello"
        ("<B-a", 0, None, [5, "hello"], "connected ascii string via 'a'"),
        # offset at 6: B=3, then -u uses 3 → "☃"
        ("<B-u", 6, None, [3, "☃"], "connected utf8 string via 'u'"),
        # Connected-width dynamic numeric types
        # offset 10: B=1, -v uses width=1 → 0x7f
        ("<B-v", 10, None, [1, 127], "connected signed int width=1"),
        # offset 10: B=1, -V uses width=1 → 0x7f
        ("<B-V", 12, None, [2, 513], "connected unsigned int width=2"),
        # offset 15: B=4, -g uses width=4 → float32 1.0
        ("<B-g", 15, None, [4, 1.0], "connected float32 width=4"),
        # offset 20: B=8, -g uses width=8 → float64 1.0
        ("<B-g", 20, None, [8, 1.0], "connected float64 width=8"),
        # Optional unpack (+)
        # At offset 0, B=5; with only 1 byte, +H has no room → skipped
        ("<B+H", 0, 2, [5], "optional skipped (no room)"),
        # At offset 0, B=5; with 4 bytes total, +H reads from 'he' → 0x6865
        ("<B+H", 0, 3, [5, 25960], "optional succeeds (partial string bytes)"),
        # Full buffer: same behavior, +H still reads from 'he'
        ("<B+H", 0, None, [5, 25960], "optional succeeds on full buffer"),
        # Consume remaining (*)
        # Start at offset 29: B=0xaa, then *B consumes remaining 5 bytes
        # → 0xbb, 0xcc, 0xdd, 0xee, 0xff
        ("<B*B", 29, None, [170, 187, 204, 221, 238, 255], "consume remaining"),
        ("<*B", 29, None, [170, 187, 204, 221, 238, 255], "only consume remaining"),
        # Edge cases
        ("", 0, None, [], "empty fmt"),
        ("<", 0, None, [], "fmt with only endian"),
    ],
)
def test_dyn_unpack_behavior(fmt, offset, endpoint, expected, description):
    out = dyn_unpack(fmt, CANON[:endpoint], offset=offset)
    assert out == expected, f"Failed: {description}"


# ----- Validate bypasses for std struct codes are triggered -----
@pytest.mark.parametrize(
    "fmt, count, n_unpack, n_parse, n_recurse, description",
    [
        ("<B5sB5sB5sB5s", 4, 1, 0, 0, "root fast path"),  # root fast path
        ("<B5sB-aB5sB-a", 4, 8, 2, 0, "loop fast path"),  # loop fast path
        ("<B5s*B5s", 5, 3, 0, 0, "repeated fast path"),  # repeated fast path
        ("<B5s*B-a", 5, 10, 4, 4, "repeated slow path"),  # repeated slow path
    ],
)
def test_dyn_unpack_fast_paths(call_graph, fmt, count, n_unpack, n_parse, n_recurse, description):
    buffer = b"\x05Hello" * count
    buffered_print(f"Testing fmt={fmt} on buffer: {buffer}")

    dyn_unpack(fmt, buffer)

    unpack_count = sum(1 for c in call_graph if c[0] == "unpack")
    parse_count = sum(1 for c in call_graph if c[0] == "parse")
    recurse_count = sum(1 for c in call_graph if c[0] == "recurse")

    assert unpack_count == n_unpack, f"Failed unpack count: {description}"
    assert parse_count == n_parse, f"Failed parse count: {description}"
    assert recurse_count == n_recurse, f"Failed recurse count: {description}"


# ------------------------------------------------------------
set_section("Tests for dyn_pack_str")
# ------------------------------------------------------------


@pytest.mark.parametrize(
    "fmt, value, encoding, return_fmt, expected_bytes, expected_fmt, description",
    [
        # 1) No integer prefix, raw bytes
        ("<s", b"hi", "utf-8", False, b"hi", "<2s", "raw bytes, no prefix"),
        # 2) No integer prefix, Python string
        ("u", "☃", "utf-8", False, b"\xe2\x98\x83", "<3s", "utf8 string, no prefix"),
        # 3) ASCII mode
        ("a", "hé", "utf-8", False, b"h?", "<2s", "ascii replace mode"),
        # 4) With integer prefix
        (
            "<Is",
            "hello",
            "utf-8",
            False,
            b"\x05\x00\x00\x00hello",
            "<I5s",
            "length-prefixed utf8 string",
        ),
        # 5) With integer prefix + return_fmt
        (
            "<Hs",
            b"abc",
            "utf-8",
            True,
            b"\x03\x00abc",
            "<H3s",
            "length-prefixed bytes with return_fmt",
        ),
        # 6) '-' prefix ignored
        ("<I-s", "yo", "utf-8", False, b"\x02\x00\x00\x00yo", "<I2s", "dash prefix ignored"),
    ],
)
def test_dyn_pack_str(fmt, value, encoding, return_fmt, expected_bytes, expected_fmt, description):
    out = dyn_pack_str(fmt, value, encoding=encoding, return_fmt=return_fmt)

    if return_fmt:
        packed, fmt_out = out
        assert packed == expected_bytes, f"Failed: {description}"
        assert fmt_out == expected_fmt, f"Failed: {description}"
    else:
        assert out == expected_bytes, f"Failed: {description}"


@pytest.mark.parametrize(
    "fmt, str_len, description",
    [
        ("", 1, "empty fmt"),
        ("<BBs", 1, "too many codes"),
        ("<Ic", 1, "invalid string code"),
        ("<bs", 200, "cannot represent length with integer code"),
        ("<fs", 1, "invalid integer code"),
    ],
)
def test_dyn_pack_str_errors(fmt, str_len, description):
    with pytest.raises(ValueError) as excinfo:
        dyn_pack_str(fmt, "x" * str_len)
    print_test_result(description, error=excinfo)  # )


# ------------------------------------------------------------
set_section("Tests for dyn_pack_num")
# ------------------------------------------------------------


@pytest.mark.parametrize(
    "fmt, value, return_fmt, expected_bytes, expected_fmt, description",
    [
        # 1) Basic numeric pack
        ("<I", 5, False, struct.pack("<I", 5), "<I", "basic unsigned int"),
        # 2) Dynamic signed int (v)
        # value=127 fits in 1 byte
        ("v", 127, False, struct.pack("<b", 127), "<b", "dynamic signed int width=1"),
        # 3) Dynamic unsigned int (V)
        # value=300 fits in 2 bytes
        ("V", 300, False, struct.pack("<H", 300), "<H", "dynamic unsigned int width=2"),
        # 4) Dynamic float (g)
        # 1.0 fits in 4 bytes
        ("g", 1.0, False, struct.pack("<f", 1.0), "<f", "dynamic float width=4"),
        # 5) With integer prefix
        # prefix stores size of numeric type
        ("<Iv", 200, True, struct.pack("<Ih", 2, 200), "<Ih", "length-prefixed dynamic int"),
        # 6) '-' prefix ignored
        ("-v", 10, False, struct.pack("<b", 10), "<b", "dash prefix ignored"),
    ],
)
def test_dyn_pack_num(fmt, value, return_fmt, expected_bytes, expected_fmt, description):
    out = dyn_pack_num(fmt, value, return_fmt=return_fmt)

    if return_fmt:
        packed, fmt_out = out
        assert packed == expected_bytes, f"Failed: {description}"
        assert fmt_out == expected_fmt, f"Failed: {description}"
    else:
        assert out == expected_bytes, f"Failed: {description}"


@pytest.mark.parametrize(
    "fmt, value, description",
    [
        ("", 1, "empty fmt"),
        ("<BBH", 1, "too many codes"),
        ("<Iz", 1, "invalid numeric code"),
        ("<Iv", 1e300, "value out of range for dynamic int"),
        ("<Zv", 5, "invalid integer prefix code"),
        ("<?d", 1e300, "integer prefix cannot represent size"),
    ],
)
def test_dyn_pack_num_errors(fmt, value, description):
    with pytest.raises(ValueError) as excinfo:
        dyn_pack_num(fmt, value)
    print_test_result(description, error=excinfo)
