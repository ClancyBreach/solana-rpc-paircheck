"""Preserved core: correlate IDs and count status slots, not transactions."""

from dataclasses import dataclass
from typing import Literal


@dataclass(frozen=True)
class CheckResult:
    outcome: Literal["consistent", "inconsistent", "not_checkable"]
    reason: str
    requested_count: int | None = None
    returned_count: int | None = None
    null_count: int | None = None


def check_pair(request: object, response: object) -> CheckResult:
    """Check correlation and counts only, never transaction success."""
    if (
        not isinstance(request, dict)
        or not isinstance(response, dict)
        or request.get("jsonrpc") != "2.0"
        or response.get("jsonrpc") != "2.0"
        or request.get("method") != "getSignatureStatuses"
    ):
        return CheckResult("not_checkable", "unsupported_shape")

    request_id, response_id = request.get("id"), response.get("id")
    # bool is an int subclass in Python. Floats are outside this small profile;
    # this is not a statement that all numeric JSON-RPC IDs must be integers.
    if type(request_id) not in (int, str) or type(response_id) not in (int, str):
        return CheckResult("not_checkable", "uncorrelated_id")
    if request_id != response_id:
        return CheckResult("inconsistent", "id_mismatch")
    if "error" in response:
        reason = "ambiguous_response" if "result" in response else "rpc_error"
        return CheckResult("not_checkable", reason)

    params, result = request.get("params"), response.get("result")
    if not isinstance(params, list) or not params or not isinstance(result, dict):
        return CheckResult("not_checkable", "unsupported_shape")
    signatures, statuses = params[0], result.get("value")
    if (
        not isinstance(signatures, list)
        or not all(isinstance(value, str) for value in signatures)
        or not isinstance(statuses, list)
        or not all(value is None or isinstance(value, dict) for value in statuses)
    ):
        return CheckResult("not_checkable", "unsupported_shape")

    counts = (len(signatures), len(statuses), sum(value is None for value in statuses))
    if counts[0] != counts[1]:
        return CheckResult("inconsistent", "count_mismatch", *counts)
    return CheckResult("consistent", "core_checks_match", *counts)
