"""FR-006 command-line interface for read and bounded personal collections."""

from __future__ import annotations

import argparse
import json
import os
import sys
from typing import Mapping, TextIO

from .credential_lifecycle import (
    Clock,
    CredentialError,
    CredentialStore,
    OAuthTransport,
    default_credential_store,
    resolve_user_access_token,
)
from .url_parser import InvalidStatusUrl, extract_post_id
from .x_api import RateLimitMetadata, Transport, XApiError, lookup_post_with_diagnostics, lookup_bookmarks, lookup_likes

_BEARER_ENV = "X_CONTEXT_BEARER_TOKEN"
_USER_TOKEN_ENV = "X_CONTEXT_USER_ACCESS_TOKEN"
_OAUTH_CLIENT_ID_ENV = "X_CONTEXT_OAUTH_CLIENT_ID"
_LOCAL_ERROR_CATEGORIES = frozenset({"invalid_input", "configuration_error"})
_CREDENTIAL_LOCAL_CATEGORIES = frozenset(
    {"credential_missing", "credential_expired", "credential_storage_error"}
)


class _CliUsageError(ValueError):
    pass


class _Parser(argparse.ArgumentParser):
    def error(self, message: str) -> None:
        # Do not echo arbitrary argv values into diagnostics.
        raise _CliUsageError("invalid_input")


def _build_parser() -> argparse.ArgumentParser:
    parser = _Parser(prog="x-context", add_help=True)
    subparsers = parser.add_subparsers(dest="command", required=True)
    read_parser = subparsers.add_parser("read", add_help=True)
    read_parser.add_argument("status_url")
    for operation in ("bookmarks", "likes"):
        collection_parser = subparsers.add_parser(operation, add_help=True, allow_abbrev=False)
        collection_parser.add_argument("--max-results", type=int, default=25)
        collection_parser.add_argument("--page-token")
    return parser


def _rate_limit_dict(rate_limit: RateLimitMetadata) -> dict[str, int | None]:
    return {
        "limit": rate_limit.limit,
        "remaining": rate_limit.remaining,
        "reset": rate_limit.reset,
    }


def _write_json_line(stream: TextIO, value: dict[str, object]) -> None:
    stream.write(json.dumps(value, ensure_ascii=False, separators=(",", ":")))
    stream.write("\n")


def _write_error(
    stream: TextIO,
    *,
    category: str,
    requests_attempted: int,
    rate_limit: RateLimitMetadata | None = None,
) -> None:
    safe_rate_limit = RateLimitMetadata() if rate_limit is None else rate_limit
    _write_json_line(
        stream,
        {
            "diagnostic": "error",
            "operation": "read",
            "error_category": category,
            "provider_requests_attempted": requests_attempted,
            "returned_item_count": 0,
            "continuation_returned": False,
            "rate_limit": _rate_limit_dict(safe_rate_limit),
        },
    )


def _exit_code_for_category(category: str) -> int:
    return 2 if category in _LOCAL_ERROR_CATEGORIES else 3


def _credential_cli_category(category: str) -> str:
    # Preserve the pre-lifecycle collection CLI contract for local credential
    # absence/corruption/expiry while the library retains finer categories.
    return "configuration_error" if category in _CREDENTIAL_LOCAL_CATEGORIES else category


def main(
    argv: list[str] | None = None,
    *,
    environ: Mapping[str, str] | None = None,
    transport: Transport | None = None,
    credential_store: CredentialStore | None = None,
    oauth_transport: OAuthTransport | None = None,
    clock: Clock | None = None,
    stdout: TextIO | None = None,
    stderr: TextIO | None = None,
) -> int:
    """Run an FR-006 command and return its process exit code."""

    selected_argv = sys.argv[1:] if argv is None else argv
    selected_environ = os.environ if environ is None else environ
    selected_stdout = sys.stdout if stdout is None else stdout
    selected_stderr = sys.stderr if stderr is None else stderr

    parser = _build_parser()
    try:
        args = parser.parse_args(selected_argv)
    except _CliUsageError:
        if selected_argv and selected_argv[0] in ("bookmarks", "likes"):
            _collection_diagnostic(selected_stderr, operation=selected_argv[0], error=XApiError("invalid_input"))
            return 2
        _write_error(
            selected_stderr,
            category="invalid_input",
            requests_attempted=0,
        )
        return 2

    if args.command in ("bookmarks", "likes"):
        lifecycle_store = credential_store
        try:
            if _USER_TOKEN_ENV not in selected_environ and lifecycle_store is None:
                lifecycle_store = default_credential_store(selected_environ)
                if lifecycle_store is None:
                    raise CredentialError("credential_missing")
            resolution = resolve_user_access_token(
                environ=selected_environ,
                store=lifecycle_store,  # env override path does not touch the store
                client_id=selected_environ.get(_OAUTH_CLIENT_ID_ENV),
                transport=oauth_transport,
                now=clock,
            )
        except CredentialError as exc:
            category = _credential_cli_category(exc.category)
            credential_requests = 1 if exc.refresh_attempted or exc.revoke_attempted else 0
            _collection_diagnostic(
                selected_stderr,
                operation=args.command,
                error=XApiError(category, requests_attempted=credential_requests),
                page_size=args.max_results if 1 <= args.max_results <= 100 else None,
                credential_source=None,
                refresh_attempted=exc.refresh_attempted,
                credential_requests_attempted=credential_requests,
            )
            return _exit_code_for_category(category)

        lookup = lookup_bookmarks if args.command == "bookmarks" else lookup_likes
        credential_requests = 1 if resolution.refresh_attempted else 0
        try:
            result = lookup(
                user_access_token=resolution.access_token,
                max_results=args.max_results,
                page_token=args.page_token,
                transport=transport,
            )
        except XApiError as exc:
            _collection_diagnostic(
                selected_stderr,
                operation=args.command,
                error=exc,
                page_size=args.max_results if 1 <= args.max_results <= 100 else None,
                credential_source=resolution.source,
                refresh_attempted=resolution.refresh_attempted,
                credential_requests_attempted=credential_requests,
            )
            return _exit_code_for_category(exc.category)
        selected_stdout.write(result.envelope.to_json() + "\n")
        _collection_diagnostic(
            selected_stderr,
            operation=args.command,
            result=result,
            page_size=result.requested_page_size,
            credential_source=resolution.source,
            refresh_attempted=resolution.refresh_attempted,
            credential_requests_attempted=credential_requests,
        )
        return 0

    if args.command != "read":
        _write_error(
            selected_stderr,
            category="invalid_input",
            requests_attempted=0,
        )
        return 2

    try:
        post_id = extract_post_id(args.status_url)
    except InvalidStatusUrl:
        _write_error(
            selected_stderr,
            category="invalid_input",
            requests_attempted=0,
        )
        return 2

    bearer_token = selected_environ.get(_BEARER_ENV)
    try:
        result = lookup_post_with_diagnostics(
            post_id,
            bearer_token=bearer_token,
            transport=transport,
        )
    except XApiError as exc:
        _write_error(
            selected_stderr,
            category=exc.category,
            requests_attempted=exc.requests_attempted,
            rate_limit=exc.rate_limit,
        )
        return _exit_code_for_category(exc.category)

    selected_stdout.write(result.envelope.to_json())
    selected_stdout.write("\n")
    _write_json_line(
        selected_stderr,
        {
            "diagnostic": "usage",
            "operation": "read",
            "provider_requests_attempted": result.requests_attempted,
            "returned_item_count": len(result.envelope.items),
            "continuation_returned": result.envelope.page.next_token is not None,
            "rate_limit": _rate_limit_dict(result.rate_limit),
        },
    )
    return 0


def _collection_diagnostic(
    stream,
    *,
    operation,
    result=None,
    error=None,
    page_size=None,
    credential_source=None,
    refresh_attempted=False,
    credential_requests_attempted=0,
):
    """Per-endpoint rates are distinct budgets, never added together."""
    subject_rate = RateLimitMetadata()
    collection_rate = RateLimitMetadata()
    if result is not None:
        subject_rate, collection_rate = result.subject_rate_limit, result.rate_limit
    elif error is not None:
        if hasattr(error, "subject_rate_limit"):
            subject_rate, collection_rate = error.subject_rate_limit, error.rate_limit
        else:
            subject_rate = error.rate_limit
    base_requests = error.requests_attempted if error is not None else result.requests_attempted
    value = {
        "diagnostic": "error" if error is not None else "usage",
        "operation": operation,
        "provider_requests_attempted": base_requests + credential_requests_attempted,
        "credential_provider_requests_attempted": credential_requests_attempted,
        "credential_source": credential_source,
        "credential_refresh_attempted": bool(refresh_attempted),
        "returned_item_count": 0 if error is not None else len(result.envelope.items),
        "requested_page_size": page_size,
        "continuation_returned": False if error is not None else result.envelope.page.next_token is not None,
        "rate_limits": {"subject": _rate_limit_dict(subject_rate), operation: _rate_limit_dict(collection_rate)},
    }
    if error is not None:
        value["error_category"] = error.category
    _write_json_line(stream, value)
