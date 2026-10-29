"""Behavior tests for the deliberately narrow feasibility probe."""

from copy import deepcopy
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from solana_rpc_paircheck.core import check_pair
from solana_rpc_paircheck.reader import check_files

HERE = Path(__file__).resolve().parent
TEMP_ROOT = HERE.parent / ".checks"
DOC_REQUEST = HERE.parent / "examples" / "request.json"
DOC_RESPONSE = HERE.parent / "examples" / "response_mismatch.json"


class PairCheckTests(unittest.TestCase):
    def setUp(self):
        TEMP_ROOT.mkdir(exist_ok=True)
        # A tripwire, not a mocked RPC: all behavior below uses real local data.
        for name in ("socket.socket", "socket.create_connection"):
            guard = patch(name, side_effect=AssertionError("Network forbidden"))
            guard.start()
            self.addCleanup(guard.stop)
        self.request = {
            "jsonrpc": "2.0", "id": 7, "method": "getSignatureStatuses",
            "params": [["synthetic-a", "synthetic-b"]],
        }
        self.response = {
            "jsonrpc": "2.0", "id": 7,
            "result": {"context": {"slot": 82}, "value": [
                {"slot": 48, "confirmations": None, "err": None,
                 "status": {"Ok": None}, "confirmationStatus": "finalized"},
                None,
            ]},
        }

    def test_matching_pair_counts_null_as_a_real_slot(self):
        result = check_pair(self.request, self.response)
        self.assertEqual(result.outcome, "consistent")
        self.assertEqual((result.requested_count, result.returned_count,
                          result.null_count), (2, 2, 1))

    def test_equal_string_ids_match(self):
        self.request["id"] = self.response["id"] = "request-7"
        self.assertEqual(check_pair(self.request, self.response).outcome, "consistent")

    def test_different_integer_ids_are_a_proven_mismatch(self):
        self.response["id"] = 8
        result = check_pair(self.request, self.response)
        self.assertEqual((result.outcome, result.reason),
                         ("inconsistent", "id_mismatch"))

    def test_string_and_integer_ids_are_not_interchangeable(self):
        self.response["id"] = "7"
        self.assertEqual(check_pair(self.request, self.response).reason, "id_mismatch")

    def test_boolean_id_is_not_accepted_as_integer_one(self):
        self.request["id"], self.response["id"] = 1, True
        self.assertEqual(check_pair(self.request, self.response).outcome, "not_checkable")

    def test_float_ids_are_outside_this_probe_not_declared_protocol_invalid(self):
        self.request["id"] = self.response["id"] = 7.0
        self.assertEqual(check_pair(self.request, self.response).outcome, "not_checkable")

    def test_null_ids_do_not_prove_correlation(self):
        self.request["id"] = self.response["id"] = None
        self.assertEqual(check_pair(self.request, self.response).outcome, "not_checkable")

    def test_missing_id_is_not_a_mismatched_known_id(self):
        del self.response["id"]
        self.assertEqual(check_pair(self.request, self.response).outcome, "not_checkable")

    def test_rpc_error_has_no_status_count_to_compare(self):
        response = {"jsonrpc": "2.0", "id": 7,
                    "error": {"code": -32602, "message": "Invalid params"}}
        result = check_pair(self.request, response)
        self.assertEqual((result.outcome, result.reason),
                         ("not_checkable", "rpc_error"))

    def test_null_id_error_is_not_called_a_transaction_failure(self):
        response = {"jsonrpc": "2.0", "id": None,
                    "error": {"code": -32700, "message": "Parse error"}}
        self.assertEqual(check_pair(self.request, response).outcome, "not_checkable")

    def test_known_id_mismatch_is_found_even_without_count_data(self):
        self.response = {"jsonrpc": "2.0", "id": 99, "error": {"code": -1}}
        self.assertEqual(check_pair(self.request, self.response).reason, "id_mismatch")

    def test_too_many_statuses_are_a_proven_count_mismatch(self):
        self.response["result"]["value"].append(None)
        result = check_pair(self.request, self.response)
        self.assertEqual((result.outcome, result.reason),
                         ("inconsistent", "count_mismatch"))
        self.assertEqual((result.requested_count, result.returned_count), (2, 3))

    def test_dropping_a_null_status_would_create_a_count_mismatch(self):
        self.response["result"]["value"].pop()
        self.assertEqual(check_pair(self.request, self.response).reason, "count_mismatch")

    def test_all_null_statuses_are_counted_without_becoming_failures(self):
        self.response["result"]["value"] = [None, None]
        result = check_pair(self.request, self.response)
        self.assertEqual((result.outcome, result.null_count), ("consistent", 2))

    def test_duplicate_signatures_are_not_deduplicated(self):
        self.request["params"][0] = ["synthetic-a", "synthetic-a"]
        self.assertEqual(check_pair(self.request, self.response).outcome, "consistent")

    def test_empty_request_and_status_lists_match(self):
        self.request["params"][0] = []
        self.response["result"]["value"] = []
        result = check_pair(self.request, self.response)
        self.assertEqual((result.outcome, result.requested_count,
                          result.returned_count, result.null_count), ("consistent", 0, 0, 0))

    def test_unsupported_shapes_do_not_get_a_clean_verdict(self):
        for side, key, value in [
            ("request", "method", "getTransaction"),
            ("request", "params", {}),
            ("request", "params", [None]),
            ("request", "params", [[7]]),
            ("response", "result", None),
            ("response", "result", {"value": "not-an-array"}),
            ("response", "result", {"value": [41, None]}),
            ("response", "jsonrpc", "1.0"),
        ]:
            with self.subTest(side=side, key=key, value=value):
                request, response = deepcopy(self.request), deepcopy(self.response)
                (request if side == "request" else response)[key] = value
                self.assertEqual(check_pair(request, response).outcome, "not_checkable")
        self.assertEqual(check_pair([self.request], self.response).outcome, "not_checkable")

    def test_ambiguous_result_and_error_are_not_guessed(self):
        self.response["error"] = {"code": -1}
        self.assertEqual(check_pair(self.request, self.response).outcome, "not_checkable")

    def test_input_objects_including_null_positions_remain_unchanged(self):
        before = deepcopy((self.request, self.response))
        check_pair(self.request, self.response)
        self.assertEqual((self.request, self.response), before)

    def test_documentation_pattern_reproduces_the_one_vs_two_problem(self):
        result = check_files(DOC_REQUEST, DOC_RESPONSE)
        self.assertEqual((result.outcome, result.reason),
                         ("inconsistent", "count_mismatch"))
        self.assertEqual((result.requested_count, result.returned_count,
                          result.null_count), (1, 2, 1))

    def test_reading_files_does_not_rewrite_them(self):
        before = (DOC_REQUEST.read_bytes(), DOC_RESPONSE.read_bytes())
        check_files(DOC_REQUEST, DOC_RESPONSE)
        self.assertEqual((DOC_REQUEST.read_bytes(), DOC_RESPONSE.read_bytes()), before)

    def test_synthetic_matching_files_use_the_real_reader(self):
        with tempfile.TemporaryDirectory(dir=TEMP_ROOT) as temp:
            directory = Path(temp).resolve()
            self.assertTrue(directory.is_relative_to(TEMP_ROOT))
            request_path, response_path = directory / "request.json", directory / "response.json"
            request_path.write_text(json.dumps(self.request), encoding="utf-8")
            response_path.write_text(json.dumps(self.response), encoding="utf-8")
            result = check_files(request_path, response_path)
            self.assertEqual((result.outcome, result.requested_count,
                              result.returned_count, result.null_count), ("consistent", 2, 2, 1))

    def test_unreadable_file_is_not_a_proven_pair_mismatch(self):
        result = check_files(DOC_REQUEST, HERE / "missing-file.json")
        self.assertEqual((result.outcome, result.reason),
                         ("not_checkable", "unreadable_json"))

    def test_invalid_and_ambiguous_json_is_not_silently_normalized(self):
        for text in ("{", '{"id":7,"id":8}', '{"id":NaN}'):
            with self.subTest(text=text), tempfile.TemporaryDirectory(dir=TEMP_ROOT) as temp:
                path = Path(temp).resolve()
                self.assertTrue(path.is_relative_to(TEMP_ROOT))
                candidate = path / "response.json"
                candidate.write_text(text, encoding="utf-8")
                result = check_files(DOC_REQUEST, candidate)
                self.assertEqual((result.outcome, result.reason),
                                 ("not_checkable", "unreadable_json"))

    def test_two_direct_assertions_also_detect_the_documented_problem(self):
        request = json.loads(DOC_REQUEST.read_text(encoding="utf-8"))
        response = json.loads(DOC_RESPONSE.read_text(encoding="utf-8"))
        with self.assertRaises(AssertionError):
            assert request["id"] == response["id"]
            assert len(request["params"][0]) == len(response["result"]["value"])
        self.assertEqual(check_files(DOC_REQUEST, DOC_RESPONSE).reason, "count_mismatch")

    def test_naive_assertions_miss_boolean_integer_id_ambiguity(self):
        self.request["id"], self.response["id"] = 1, True
        assert self.request["id"] == self.response["id"]
        assert len(self.request["params"][0]) == len(self.response["result"]["value"])
        self.assertEqual(check_pair(self.request, self.response).outcome, "not_checkable")
