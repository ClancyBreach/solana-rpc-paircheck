import json
from pathlib import Path
import subprocess
import sys

from .support import EXAMPLES, PROJECT, OfflineCase


class CliTests(OfflineCase):
    def test_text_report_and_code_zero_for_matching_core(self):
        code, output, error = self.invoke(str(self.request), str(self.response))
        self.assertEqual(code, 0)
        self.assertIn("consistent", output)
        self.assertIn("1", output)
        self.assertEqual(error, "")

    def test_json_report_has_documented_fields_and_correct_null_count(self):
        code, output, error = self.invoke(str(self.request), str(self.response), "--json")
        payload = json.loads(output)
        self.assertEqual(code, 0)
        self.assertEqual(payload["outcome"], "consistent")
        self.assertEqual((payload["requested_count"], payload["returned_count"], payload["null_count"]),
                         (1, 1, 1))
        self.assertIn("scope", payload)
        self.assertEqual(error, "")

    def test_count_mismatch_is_code_one(self):
        code, output, error = self.invoke(str(self.request), str(EXAMPLES / "response_mismatch.json"), "--json")
        self.assertEqual(code, 1)
        payload = json.loads(output)
        self.assertEqual((payload["outcome"], payload["reason"]), ("inconsistent", "count_mismatch"))
        self.assertEqual((payload["requested_count"], payload["returned_count"]), (1, 2))
        self.assertEqual(error, "")

    def test_missing_input_is_code_two_without_echoing_path(self):
        path = self.directory / "DO_NOT_ECHO_FILE.json"
        code, output, error = self.invoke(str(self.request), str(path), "--json")
        self.assertEqual(code, 2)
        self.assertEqual(json.loads(output)["outcome"], "not_checkable")
        self.assertNotIn("DO_NOT_ECHO", output + error)

    def test_rpc_error_does_not_become_a_transaction_failure(self):
        self.response.write_text(
            '{"jsonrpc":"2.0","id":1,"error":{"code":-1,"message":"DO_NOT_ECHO"}}',
            encoding="utf-8",
        )
        code, output, error = self.invoke(str(self.request), str(self.response), "--json")
        self.assertEqual(code, 2)
        self.assertEqual(json.loads(output)["reason"], "rpc_error")
        self.assertNotIn("DO_NOT_ECHO", output + error)

    def test_extra_input_content_is_not_dumped(self):
        payload = json.loads(self.response.read_text(encoding="utf-8"))
        payload["provider"] = "https://example.invalid/?key=DO_NOT_ECHO\u001b[31m"
        self.response.write_text(json.dumps(payload), encoding="utf-8")
        for flags in ((), ("--json",)):
            with self.subTest(flags=flags):
                code, output, error = self.invoke(str(self.request), str(self.response), *flags)
                self.assertEqual(code, 0)
                self.assertNotIn("DO_NOT_ECHO", output + error)
                self.assertNotIn("\u001b", output + error)

    def test_json_report_is_deterministic_across_invocations(self):
        first = self.invoke(str(self.request), str(self.response), "--json")
        self.assertEqual(first, self.invoke(str(self.request), str(self.response), "--json"))
        self.assertEqual(first[0], 0)

    def test_missing_arguments_are_controlled_usage_errors(self):
        code, output, error = self.invoke()
        self.assertEqual(code, 2)
        self.assertEqual(output, "")
        self.assertIn("--help", error)
        self.assertNotIn("Traceback", error)

    def test_unknown_arguments_do_not_echo_their_values(self):
        code, output, error = self.invoke("--DO_NOT_ECHO=PRIVATE")
        self.assertEqual(code, 2)
        self.assertIn("--help", error)
        self.assertNotIn("DO_NOT_ECHO", output + error)

    def test_help_and_version_do_not_require_input_files(self):
        for option in ("--help", "--version"):
            with self.subTest(option=option):
                code, output, error = self.invoke(option)
                self.assertEqual(code, 0)
                self.assertIn("solana-rpc-paircheck", output)
                self.assertEqual(error, "")

    def run_module(self, *arguments):
        # Guard the child as well; parent mocks do not cross process boundaries.
        script = (
            "import runpy,socket,sys\n"
            f"sys.path.insert(0,{str(PROJECT / 'src')!r})\n"
            "def forbidden(*a,**k): raise AssertionError('Network forbidden')\n"
            "socket.socket=socket.create_connection=forbidden\n"
            "sys.argv=['solana-rpc-paircheck',*sys.argv[1:]]\n"
            "runpy.run_module('solana_rpc_paircheck',run_name='__main__')\n"
        )
        return subprocess.run(
            [sys.executable, "-I", "-S", "-B", "-c", script, *arguments],
            capture_output=True, text=True, timeout=5, cwd=self.directory,
        )

    def test_module_entrypoint_has_real_process_codes_with_network_blocked(self):
        cases = [
            (self.response, 0, "consistent"),
            (EXAMPLES / "response_mismatch.json", 1, "inconsistent"),
            (self.directory / "missing.json", 2, "not_checkable"),
        ]
        for path, expected_code, outcome in cases:
            with self.subTest(path=path):
                result = self.run_module(str(self.request), str(path), "--json")
                self.assertEqual(result.returncode, expected_code)
                self.assertEqual(json.loads(result.stdout)["outcome"], outcome)
                self.assertEqual(result.stderr, "")

    def test_subprocess_output_is_deterministic(self):
        args = (str(self.request), str(self.response), "--json")
        first, second = self.run_module(*args), self.run_module(*args)
        self.assertEqual(first.returncode, 0)
        self.assertEqual((first.stdout, first.stderr), (second.stdout, second.stderr))
