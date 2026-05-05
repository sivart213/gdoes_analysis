from testing.helpers import color_wrap, buffered_print

# ------------------------------------------------------------
# Helpers
# ------------------------------------------------------------


def print_test_result(msg="", warnings=None, error=None):
    """Render test result summary to console with color coding."""

    # Header line
    if msg:
        buffered_print(f"Error/Warning/Ignore test output(s).  Context: {msg}")
    else:
        buffered_print("Error/Warning/Ignore test output(s).")

    if error is not None:
        msg = ""
        try:
            lines = str(error.getrepr(style="line")).splitlines()
        except Exception:
            msg = color_wrap("Error", "light_red")
            msg += ": " + color_wrap(
                "unable to extract error message suggesting failed test", "red"
            )
            buffered_print(msg)
            return

        for line in lines:
            if line.strip() and "the above exception" not in line.lower():
                line = line.strip()
                if line.startswith("E "):
                    line = line[1:].strip()
                typ, err = line.split(":", 1)
                if msg:
                    msg += " -> "
                msg += f"{color_wrap(typ, 'light_red')}: {color_wrap(err.strip(), 'red')}"
        buffered_print(msg)

    if warnings is not None:
        try:
            for w in warnings or []:
                buffered_print(
                    f"{color_wrap('Warning', 'light_yellow')}: {color_wrap(str(w.message), 'yellow')}"
                )
        except Exception:
            buffered_print(
                f"{color_wrap('Warning', 'light_yellow')}: {color_wrap('unable to extract warning message suggesting failed test', 'yellow')}"
            )

    if warnings is None and error is None:
        buffered_print(
            f"{color_wrap('Ignore', 'light_green')}: {color_wrap('No errors or warnings during test.', 'green')}"
        )
