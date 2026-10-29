"""Small offline command-line interface with deterministic reports."""

import argparse
from dataclasses import asdict
import json

from . import __version__
from .core import CheckResult
from .reader import check_files

SCOPE = ("getSignatureStatuses IDs and list lengths only. Does not verify "
         "transaction authenticity, execution success, or finality.")
EXIT_CODES = {"consistent": 0, "inconsistent": 1, "not_checkable": 2}
REASONS = {
    "core_checks_match": "Supported IDs and list lengths match.",
    "id_mismatch": "Known request and response IDs differ.",
    "count_mismatch": "Signature count and returned status-slot count differ.",
    "uncorrelated_id": "An ID is missing, null, or outside the integer/string profile.",
    "unsupported_shape": "Method or document shape is outside the supported profile.",
    "rpc_error": "An RPC error provides no status list to compare.",
    "ambiguous_response": "The response contains both result and error.",
    "unreadable_json": "A file is unavailable, unreadable, or not unambiguous UTF-8 JSON.",
    "file_too_large": "A file exceeds the 1 MiB byte limit.",
    "nesting_too_deep": "A document exceeds 64 nested containers.",
    "non_regular_file": "Input must be a regular file.",
    "non_local_path": "URL, UNC, and device-namespace sources are not accepted.",
}


class _Parser(argparse.ArgumentParser):
    def error(self, message):
        # Default argparse errors may echo arbitrary argument values.
        self.exit(2, "Invalid arguments. Use --help for usage.\n")


def _report(result: CheckResult, as_json: bool) -> str:
    if as_json:
        payload = asdict(result)
        payload["scope"] = SCOPE
        return json.dumps(payload, sort_keys=True, indent=2, ensure_ascii=True)
    counts = ["not checked" if value is None else str(value) for value in
              (result.requested_count, result.returned_count, result.null_count)]
    return (f"Outcome: {result.outcome}\n"
            f"Reason: {REASONS[result.reason]}\n"
            f"Requested signatures: {counts[0]}\n"
            f"Returned status slots: {counts[1]}\n"
            f"Null status slots: {counts[2]}\n"
            f"Scope: {SCOPE}")


def main(argv: list[str] | None = None) -> int:
    parser = _Parser(prog="solana-rpc-paircheck", description=SCOPE)
    parser.add_argument("request", help="Path to the local JSON-RPC request file")
    parser.add_argument("response", help="Path to the local JSON-RPC response file")
    parser.add_argument("--json", dest="as_json", action="store_true",
                        help="Write the deterministic machine-readable report")
    parser.add_argument("--version", action="version",
                        version=f"%(prog)s {__version__}")
    args = parser.parse_args(argv)
    result = check_files(args.request, args.response)
    print(_report(result, args.as_json))
    return EXIT_CODES[result.outcome]
