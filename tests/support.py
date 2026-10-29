from contextlib import redirect_stderr, redirect_stdout
from io import StringIO
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from solana_rpc_paircheck.cli import main

PROJECT = Path(__file__).resolve().parents[1]
EXAMPLES = PROJECT / "examples"


class OfflineCase(unittest.TestCase):
    def setUp(self):
        for name in ("socket.socket", "socket.create_connection"):
            self.enterContext(patch(name, side_effect=AssertionError("Network forbidden")))
        checks = PROJECT / ".checks"
        checks.mkdir(exist_ok=True)
        self.directory = Path(self.enterContext(tempfile.TemporaryDirectory(dir=checks))).resolve()
        self.assertTrue(self.directory.is_relative_to(PROJECT))
        self.request = self.directory / "request.json"
        self.response = self.directory / "response.json"
        self.request.write_bytes((EXAMPLES / "request.json").read_bytes())
        self.response.write_bytes((EXAMPLES / "response.json").read_bytes())

    def invoke(self, *args):
        stdout, stderr = StringIO(), StringIO()
        with redirect_stdout(stdout), redirect_stderr(stderr):
            try:
                code = main(list(args))
            except SystemExit as exc:
                code = exc.code
        return code, stdout.getvalue(), stderr.getvalue()
