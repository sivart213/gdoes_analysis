# import logging

# from testing.helpers import print_buffer, buffered_print

# # def test_print_normal(show_capture_mode):
# #     print("[test_print_normal] normal print")


# # def test_print_buffered(show_capture_mode):
# #     buffered_print("[test_print_buffered] buffered print 1")
# #     buffered_print("[test_print_buffered] buffered print 2")
# #     print("[test_print_buffered] after buffered prints (should appear normal flush)")


# def test_print_flush_buffer(show_capture_mode):
#     buffered_print("[test_print_flush_buffer] buffered print 1")
#     print("[test_print_flush_buffer] normal print (before flush)")
#     print_buffer()
#     print("[test_print_flush_buffer] normal print (after flush)")
#     print_buffer()
#     print(
#         "[test_print_flush_buffer] normal print (after 2nd flush) (should not duplicate buffered print)"
#     )


# # def test_print_capture(capsys):
# #     print("hello from test")
# #     out, err = capsys.readouterr()
# #     print("=== captured stdout ===")
# #     print(out)


# # def helper():
# #     print("[helper] normal print")
# #     buffered_print("[helper] buffered print A")
# #     buffered_print("[helper] buffered print B")


# # def test_print_capture_behavior(capsys):
# #     # Call helper (prints + buffered prints)
# #     helper()

# #     # Read what pytest captured
# #     captured = capsys.readouterr()
# #     # assert captured.out == "[helper] normal print\n"  # Only the normal print is captured

# #     print("=== captured stdout before flush ===")
# #     print(captured.out)

# #     # Flush buffer (simulating reporter flush)
# #     print_buffer()

# #     print("=== flush complete ===")
# #     # Read what pytest captured
# #     captured = capsys.readouterr()

# #     print("=== captured stdout after flush ===")
# #     print(captured.out)


# def test_print_buffered_output_held(capsys):
#     print("normal print")
#     buffered_print("buffered A")
#     buffered_print("buffered B")

#     captured = capsys.readouterr()

#     print("=== captured stdout ===")
#     print(captured.out)


# def test_print_buffered_output_printed(capsys):
#     print("normal print")
#     buffered_print("buffered A")
#     buffered_print("buffered B")

#     print_buffer()

#     captured = capsys.readouterr()

#     print("=== captured stdout ===")
#     print(captured.out)


# def test_print_buffered_delay(request, capsys, caplog):
#     """
#     Validate that buffered_print delays output only when capture mode
#     is 'no' or 'tee-sys'. In other modes, buffered_print should behave
#     like a normal print and appear immediately in captured output.
#     """

#     mode = request.config.getoption("capture")
#     is_default = request.config.getoption("--default-reporter")

#     # Emit one normal print and one buffered print
#     print("[normal]")
#     buffered_print("[buffered]")
#     logging.getLogger().warning("[log] warning message")

#     # BEFORE FLUSH: inspect captured output
#     captured = capsys.readouterr()

#     if mode in {"no", "tee-sys"} and not is_default:
#         # Buffered output should NOT appear yet
#         assert "[normal]" in captured.out
#         assert "[buffered]" not in captured.out
#         # Now flush the buffer
#         combined = captured.out
#         print_buffer()

#         # AFTER FLUSH: inspect captured output again
#         captured = capsys.readouterr()

#         # After flush, buffered output must appear in all modes
#         assert "[buffered]" in captured.out

#         combined += captured.out

#         # normal_index = combined.index("[normal]")
#         # buffered_index = combined.index("[buffered]")
#         # assert normal_index < buffered_index

#     else:
#         # Buffered output should appear immediately (no buffering)
#         assert "[normal]" in captured.out
#         assert "[buffered]" in captured.out
#         combined = captured.out

#     normal_index = combined.index("[normal]")
#     buffered_index = combined.index("[buffered]")
#     assert normal_index < buffered_index

#     assert "[log] warning message" in caplog.text

#     # # Now flush the buffer
#     # print_buffer()

#     # # AFTER FLUSH: inspect captured output again
#     # captured = capsys.readouterr()

#     # # After flush, buffered output must appear in all modes
#     # assert "[buffered]" in captured.out


# # def test_print_logging_demo():
# #     handler = logging.StreamHandler(sys.stdout)
# #     logging.getLogger().addHandler(handler)
# #     logging.getLogger().setLevel(logging.INFO)

# #     logging.info("hello from logger")
# #     print("hello from print")
