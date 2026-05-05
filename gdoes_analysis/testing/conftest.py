import struct

import pytest

from testing.helpers import color_wrap, buffered_print
from gdoes_analysis.parse_tools import struct_tools


@pytest.fixture
def override_parse_output(monkeypatch):
    """
    Monkeypatch parse_dyn_syntax so tests can dynamically override
    the first element of its return tuple (fmt).

    Usage:
        set_output = override_parse_output
        set_output("X")   # force fmt="X"
        set_output(None)  # restore normal behavior
    """

    real_parse = struct_tools.parse_dyn_syntax
    override = {"fmt": None}  # mutable cell

    def fake_parse(prefix, code, space, out, endian="<"):
        res = real_parse(prefix, code, space, out, endian=endian)

        buffered_print(
            f"{color_wrap('[fake_parse]', 'light_gold')} CALLED with {res[0]!r} replaced by {override['fmt']!r}"
        )

        # Override first output if requested
        if override["fmt"] is not None:
            # Return a new tuple with fmt replaced
            return (override["fmt"],) + tuple(res[1:])

        return res

    monkeypatch.setattr(struct_tools, "parse_dyn_syntax", fake_parse)

    def controller(new_fmt):
        """
        Set or clear the override for the first return value.
        new_fmt=None restores normal behavior.
        """
        override["fmt"] = new_fmt

    return controller


@pytest.fixture
def call_graph(monkeypatch):
    calls = []

    real_unpack = struct.unpack_from

    # patch struct.unpack_from
    def fake_unpack(fmt, data, pos):
        calls.append(("unpack", fmt))
        # buffered_print(f"[fake_unpack] CALLED with fmt={fmt!r}, pos={pos}")
        buffered_print(
            f"{color_wrap('[fake_unpack]', 'pirate_gold')} CALLED with fmt={fmt!r}, pos={pos}"
        )
        return real_unpack(fmt, data, pos)

    monkeypatch.setattr(struct, "unpack_from", fake_unpack)

    # patch parse_dyn_syntax
    real_parse = struct_tools.parse_dyn_syntax

    def fake_parse(prefix, code, space, out, endian="<"):
        calls.append(("parse", code))
        res = real_parse(prefix, code, space, out, endian=endian)
        buffered_print(
            f"{color_wrap('[fake_parse]', 'light_gold')} CALLED with prefix/code={prefix!r}/{code!r}, returned fmt={res[0]!r}"
        )
        return res

    monkeypatch.setattr(struct_tools, "parse_dyn_syntax", fake_parse)

    # patch dyn_unpack recursion
    real_dyn_unpack = struct_tools.dyn_unpack

    def fake_dyn(fmt, data, offset, **kw):
        calls.append(("recurse", fmt))
        buffered_print(
            f"{color_wrap('[fake_dyn]', 'harvest_gold')} CALLED with fmt={fmt!r}, pos={offset}"
        )
        return real_dyn_unpack(fmt, data, offset, **kw)

    monkeypatch.setattr(struct_tools, "dyn_unpack", fake_dyn)

    return calls
