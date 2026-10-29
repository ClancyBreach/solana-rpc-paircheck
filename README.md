# Solana RPC Paircheck

Check **core consistency** between two local Solana JSON-RPC files. Only
`getSignatureStatuses` is supported. A matching report does **not** verify
transaction authenticity, execution success, finality, or complete RPC validity.

Python 3.11+; **no runtime dependencies, network client, wallet, or signing code**.
Local verification uses Windows and Python 3.11.9. The GitHub Actions workflow
runs the same standard-library test suite on Windows and Linux with Python 3.11.

## Install locally, offline

From this directory, build a wheel using a Python environment that already has
setuptools 77.0.3+ (build dependency only). No package download is performed:

```powershell
python -m pip wheel --no-index --no-deps --no-build-isolation --no-cache-dir . --wheel-dir dist
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install --no-index --no-deps dist\solana_rpc_paircheck-0.1.0-py3-none-any.whl
```

The build requires setuptools to be installed beforehand; the runtime does not.
Local verification used setuptools 83.0.0. If the offline prerequisite is absent,
the build fails rather than downloading it. The package is not published on PyPI.

On Linux, use `.venv/bin/python` and `.venv/bin/solana-rpc-paircheck`
instead of the Windows `Scripts` paths shown below.

## Use

```powershell
.\.venv\Scripts\solana-rpc-paircheck.exe examples/request.json examples/response.json
.\.venv\Scripts\solana-rpc-paircheck.exe examples/request.json examples/response_mismatch.json --json
.\.venv\Scripts\python.exe -m solana_rpc_paircheck --help
```

The matching example has one requested signature and one `null` status slot.
The mismatch example has two returned slots for one requested signature.
Example signatures are synthetic placeholders, not real transactions.

| Exit code | Meaning |
|---|---|
| 0 | Supported core checks match; **not** a transaction-success verdict |
| 1 | Known ID mismatch or status-slot count mismatch |
| 2 | Not checkable, unreadable input, limit exceeded, or invalid CLI arguments |

`--help` and `--version` exit 0 without checking files. Reports go to stdout;
argument-usage errors print a generic message to stderr, even with `--json`.
JSON reports contain `outcome`, `reason`, `requested_count`, `returned_count`,
`null_count`, and `scope`. Counts are `null` when not evaluated. Output has no
timestamps, raw input, IDs, file paths, or provider credentials and is deterministic.

## Supported profile and limits

- One request and one response object, both using JSON-RPC `"2.0"`.
- Only `getSignatureStatuses`; parameter zero must be an array of strings.
- Compare known **integer or string IDs**. Missing/null/boolean/float IDs are not
  checkable in this profile. JSON-RPC permits other number forms in general.
- A known ID mismatch takes precedence over unavailable count data.
- Count every `result.value` slot, including `null` and duplicate input signatures.
- Status slots may be objects or `null`. Inner fields, signatures, request limits,
  and parameter configuration are **not validated**. Even nonsensical inner status
  content can pass these core checks.
- RPC errors have no status list to compare and produce `not_checkable`.
- Strict UTF-8 JSON, no BOM/comments/batches/duplicate keys/NaN/Infinity or float
  overflow. At most **1,048,576 bytes per file** and **64 nested containers**,
  counting the root object. Depth is checked before decoding; strings do not add depth.
- Read-only regular files on local storage. URLs, UNC/device-namespace paths,
  directories and device files are refused. Use actual local files, not network
  mounts or links to remote storage; the OS determines where a mounted path resides.

Files are never rewritten. The program does not record traffic, repair fixtures,
fetch schemas or contacts, or make RPC calls. Equal IDs/counts do not prove order
or provenance. A `null` status means unavailable/unknown, not transaction failure.
Files are read sequentially, not as an atomic snapshot of concurrent edits.
Deliberately inconsistent negative fixtures can be useful tests; findings do not
judge the intent of a test author. No payment or financial verification is provided.

## Develop and test

```powershell
python -I -S -B -m unittest discover -s tests -t . -v
```

Standard-library tests block sockets, exercise the actual reader/CLI and process
exit codes, preserve input bytes, and cover byte/depth boundaries and deterministic
reports. Temporary files stay in this project's ignored `.checks/` directory.

Protocol references: [Solana getSignatureStatuses](https://solana.com/docs/rpc/http/getsignaturestatuses),
[JSON-RPC 2.0](https://www.jsonrpc.org/specification). This is a deliberately narrow
profile rather than a complete implementation of either specification.

## License and releases

Released under the [MIT License](LICENSE), copyright 2026 ClancyBreach.
Source releases are available on
[GitHub](https://github.com/ClancyBreach/solana-rpc-paircheck/releases).
No external project or company endorsement is implied.
