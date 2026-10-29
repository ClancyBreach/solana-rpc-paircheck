import json
import os
from pathlib import Path
from unittest.mock import patch

from solana_rpc_paircheck.reader import check_files
from .support import OfflineCase

LIMIT = 1024 * 1024


class ReaderTests(OfflineCase):
    def result(self):
        return check_files(self.request, self.response)

    def test_exact_byte_limit_is_accepted_without_truncation(self):
        content = self.response.read_bytes()
        self.response.write_bytes(content + b" " * (LIMIT - len(content)))
        result = self.result()
        self.assertEqual((result.outcome, result.null_count), ("consistent", 1))

    def test_one_byte_over_limit_is_not_checked(self):
        content = self.response.read_bytes()
        self.response.write_bytes(content + b" " * (LIMIT + 1 - len(content)))
        result = self.result()
        self.assertEqual((result.outcome, result.reason), ("not_checkable", "file_too_large"))

    def test_size_limit_applies_to_request_too(self):
        self.request.write_bytes(b" " * (LIMIT + 1))
        self.assertEqual(self.result().reason, "file_too_large")

    def test_limit_is_bytes_not_unicode_characters(self):
        content = '{"padding":"' + "é" * (LIMIT // 2) + '"}'
        self.assertLess(len(content), LIMIT)
        self.response.write_bytes(content.encode("utf-8"))
        self.assertEqual(self.result().reason, "file_too_large")

    def nested_response(self, levels):
        value = 0
        for _ in range(levels):
            value = [value]
        response = {"jsonrpc": "2.0", "id": 1,
                    "result": {"value": [None]}, "extra": value}
        self.response.write_text(json.dumps(response), encoding="utf-8")

    def test_depth_64_including_root_is_accepted(self):
        self.nested_response(63)
        self.assertEqual(self.result().outcome, "consistent")

    def test_depth_65_is_rejected_before_decoding(self):
        self.nested_response(64)
        self.assertEqual(self.result().reason, "nesting_too_deep")

    def test_extreme_nesting_has_a_controlled_depth_result(self):
        self.response.write_text("[" * 2000 + "0" + "]" * 2000, encoding="utf-8")
        self.assertEqual(self.result().reason, "nesting_too_deep")

    def test_brackets_quotes_and_backslashes_inside_strings_do_not_add_depth(self):
        response = {"jsonrpc": "2.0", "id": 1, "result": {"value": [None]},
                    "extra": '[\\\"{]}' * 100}
        self.response.write_text(json.dumps(response), encoding="utf-8")
        self.assertEqual(self.result().outcome, "consistent")

    def test_directory_is_not_a_regular_input_file(self):
        result = check_files(self.request, self.directory)
        self.assertEqual((result.outcome, result.reason), ("not_checkable", "non_regular_file"))

    def test_device_file_is_not_read(self):
        result = check_files(self.request, Path(os.devnull))
        self.assertEqual(result.reason, "non_regular_file")

    def test_url_and_unc_sources_never_reach_filesystem_access(self):
        for source in ("https://example.invalid/token/DO_NOT_ECHO", r"\\server\share\sample.json"):
            with self.subTest(source=source), patch(
                "solana_rpc_paircheck.reader.os.stat", side_effect=AssertionError("Remote access")
            ), patch("pathlib.Path.open", side_effect=AssertionError("Remote access")):
                self.assertEqual(check_files(Path(source), self.response).reason, "non_local_path")

    def test_permission_error_is_controlled_without_echoing_exception(self):
        with patch("solana_rpc_paircheck.reader.os.open", side_effect=PermissionError("DO_NOT_ECHO")):
            result = self.result()
        self.assertEqual((result.outcome, result.reason), ("not_checkable", "unreadable_json"))
        self.assertNotIn("DO_NOT_ECHO", repr(result))

    def test_invalid_utf8_is_not_checked(self):
        self.response.write_bytes(b"\xff\xfe")
        self.assertEqual(self.result().reason, "unreadable_json")

    def test_nonfinite_numbers_and_overflow_are_not_silently_accepted(self):
        for value in ("NaN", "Infinity", "-Infinity", "1e9999"):
            with self.subTest(value=value):
                self.response.write_text(
                    '{"jsonrpc":"2.0","id":1,"result":{"value":[null]},"extra":' + value + '}',
                    encoding="utf-8",
                )
                self.assertEqual(self.result().reason, "unreadable_json")

    def test_duplicate_keys_at_nested_levels_are_not_silently_chosen(self):
        self.response.write_text(
            '{"jsonrpc":"2.0","id":1,"result":{"value":[null],"value":[]}}', encoding="utf-8"
        )
        self.assertEqual(self.result().reason, "unreadable_json")

    def test_unknown_status_fields_remain_outside_the_check_profile(self):
        self.response.write_text(
            '{"jsonrpc":"2.0","id":1,"result":{"value":[{"err":17}]}}', encoding="utf-8"
        )
        self.assertEqual(self.result().outcome, "consistent")

    def test_request_bytes_are_unchanged_when_response_cannot_be_checked(self):
        before = self.request.read_bytes()
        self.response.write_bytes(b"broken JSON")
        self.result()
        self.assertEqual(self.request.read_bytes(), before)
