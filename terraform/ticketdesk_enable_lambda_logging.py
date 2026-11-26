#!/usr/bin/env python3
"""Add safe, structured CloudWatch audit messages to four existing TicketDesk Lambdas.

Run from the project's Terraform directory on Windows:
    python ticketdesk_enable_lambda_logging.py --deploy

Uses the already downloaded, live Lambda ZIP packages in
    %TEMP%/ticketdesk-lambda-review/

Does not change the Lambda business logic, handlers, IAM, trigger configuration,
S3 data, RDS data, or FastAPI SLA behavior. It updates the three Terraform-managed
Lambda ZIP artifacts and creates ticketdesk-file-processor-logging.zip.
"""

from __future__ import annotations

import argparse
import ast
import base64
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import zipfile

REGION = "ap-south-1"
FUNCTIONS = {
    "ticketdesk-folder-creator": ("handler.py", "ticketdesk-folder-creator.zip"),
    "ticketdesk-discussion-sync": ("handler.py", "ticketdesk-discussion-sync.zip"),
    "ticketdesk-log-processor": ("handler.py", "ticketdesk-log-processor.zip"),
    "ticketdesk-file-processor": ("lambda_function.py", "ticketdesk-file-processor-logging.zip"),
}
MARKER = "# TICKETDESK_CLOUDWATCH_AUDIT_V1"

# This wrapper observes only inputs and outputs, never changes the original handler.
# In particular, it does NOT log comment bodies, internal discussions, user names,
# ticket descriptions, changed values, or the contents of S3 JSON documents.
AUDIT_WRAPPER = r'''

# TICKETDESK_CLOUDWATCH_AUDIT_V1
import datetime as _td_datetime
import json as _td_json

_td_original_lambda_handler = lambda_handler
_td_function_name = __FUNCTION_NAME__


def _td_audit_emit(stage, **details):
    record = {
        "component": "TicketDesk",
        "function": _td_function_name,
        "stage": stage,
        "time_utc": _td_datetime.datetime.now(_td_datetime.timezone.utc).isoformat(),
    }
    record.update({k: v for k, v in details.items() if v is not None})
    print("TICKETDESK_AUDIT " + _td_json.dumps(record, ensure_ascii=False, default=str), flush=True)


def lambda_handler(event, context):
    safe = event if isinstance(event, dict) else {}
    ticket_id = safe.get("ticket_id")
    ticket_id = ticket_id if isinstance(ticket_id, str) else None
    request_id = getattr(context, "aws_request_id", None)
    common = {"request_id": request_id, "ticket_id": ticket_id}
    comment = safe.get("comment") if isinstance(safe.get("comment"), dict) else {}
    history = safe.get("history") if isinstance(safe.get("history"), dict) else {}

    s3_key = None
    if ticket_id and _td_function_name == "ticketdesk-folder-creator":
        s3_key = "TicketLogs/Tickets/" + ticket_id + "/"
    elif ticket_id and _td_function_name == "ticketdesk-discussion-sync":
        s3_key = "TicketLogs/Tickets/" + ticket_id + "/Discussiondetails.json"
    elif ticket_id and _td_function_name == "ticketdesk-log-processor":
        s3_key = "TicketLogs/Tickets/" + ticket_id + "/Logdetails/Logdetails.json"

    if _td_function_name == "ticketdesk-discussion-sync":
        common.update(comment_id=comment.get("id"), author_id=comment.get("author_id"),
                      is_internal=comment.get("is_internal") is True)
    elif _td_function_name == "ticketdesk-log-processor":
        common.update(event_id=history.get("event_id"), action=history.get("action"),
                      field_name=history.get("field_name"), actor_id=history.get("actor_id"),
                      history_created_at=history.get("created_at"))
    elif _td_function_name == "ticketdesk-file-processor":
        common.update(event_source=safe.get("source"), event_type=safe.get("detail-type"),
                      records_received=len(safe.get("Records")) if isinstance(safe.get("Records"), list) else None)
        detail = safe.get("detail") if isinstance(safe.get("detail"), dict) else {}
        obj = detail.get("object") if isinstance(detail.get("object"), dict) else {}
        bucket = detail.get("bucket") if isinstance(detail.get("bucket"), dict) else {}
        common.update(bucket=bucket.get("name"), object_key=obj.get("key"))

    _td_audit_emit("RECEIVED", **common, s3_key=s3_key)
    try:
        result = _td_original_lambda_handler(event, context)
        if isinstance(result, dict):
            status_code = result.get("statusCode")
            operation_result = result.get("result")
            if _td_function_name == "ticketdesk-folder-creator":
                folder_results = result.get("results")
                if isinstance(folder_results, dict):
                    prefix = "TicketLogs/Tickets/" + ticket_id + "/" if ticket_id else ""
                    files = {"discussion": "Discussiondetails.json", "attachments": "Attachments/", "logs": "Logdetails/"}
                    for label, result_status in folder_results.items():
                        _td_audit_emit("OBJECT_RESULT", **common, component_name=label,
                                       s3_key=prefix + files.get(label, label), result=result_status)
            elif _td_function_name == "ticketdesk-discussion-sync":
                _td_audit_emit("DOCUMENT_UPDATE", **common, s3_key=s3_key,
                               result=operation_result, status_code=status_code)
            elif _td_function_name == "ticketdesk-log-processor":
                _td_audit_emit("DOCUMENT_UPDATE", **common, s3_key=s3_key,
                               result=operation_result, status_code=status_code,
                               total_events=result.get("total_events"))
            elif _td_function_name == "ticketdesk-file-processor":
                body = result.get("body")
                if isinstance(body, str):
                    try:
                        summary = _td_json.loads(body)
                    except (TypeError, ValueError):
                        summary = {}
                    if isinstance(summary, dict):
                        for item in summary.get("items", []) if isinstance(summary.get("items"), list) else []:
                            if isinstance(item, dict):
                                _td_audit_emit("ATTACHMENT_VERIFIED", request_id=request_id,
                                               ticket_id=item.get("ticket_id"), bucket=item.get("bucket"),
                                               object_key=item.get("object_key"),
                                               file_size_bytes=item.get("file_size_bytes"),
                                               content_type=item.get("content_type"),
                                               result=item.get("status"))
                        common["processed_count"] = summary.get("processed_count")
            _td_audit_emit("SUCCEEDED", **common, s3_key=s3_key,
                           status_code=status_code, result=operation_result)
        else:
            _td_audit_emit("SUCCEEDED", **common, s3_key=s3_key)
        return result
    except Exception as error:
        # A short error message, not the full input event or sensitive S3 document.
        _td_audit_emit("FAILED", **common, s3_key=s3_key,
                       error_type=type(error).__name__, error_message=str(error)[:300])
        raise
'''


def aws_json(*args: str) -> dict:
    completed = subprocess.run(
        ["aws", *args, "--region", REGION, "--output", "json"],
        check=True, capture_output=True, text=True, encoding="utf-8"
    )
    return json.loads(completed.stdout)


def verify_download_is_live(function: str, zip_path: Path, expected_handler: str) -> None:
    details = aws_json("lambda", "get-function", "--function-name", function)
    conf = details["Configuration"]
    if conf.get("Handler") != expected_handler + ".lambda_handler":
        raise RuntimeError(f"{function}: deployed handler changed: {conf.get('Handler')}")
    content = zip_path.read_bytes()
    actual_code_sha = base64.b64encode(hashlib.sha256(content).digest()).decode("ascii")
    if actual_code_sha != conf.get("CodeSha256"):
        raise RuntimeError(
            f"{function}: downloaded ZIP does not match currently deployed Lambda. "
            "Re-download the deployed function ZIPs and rerun; nothing was changed."
        )


def add_logging(source_zip: Path, destination: Path, handler_file: str, function: str) -> None:
    with zipfile.ZipFile(source_zip, "r") as reader, zipfile.ZipFile(destination, "w") as writer:
        names = reader.namelist()
        if handler_file not in names:
            raise RuntimeError(f"{source_zip} does not contain expected {handler_file}: {names}")
        for info in reader.infolist():
            contents = reader.read(info.filename)
            if info.filename == handler_file:
                code = contents.decode("utf-8-sig")
                if MARKER in code:
                    raise RuntimeError(f"{function}: audit logging is already installed. No changes made.")
                ast.parse(code, filename=handler_file)
                wrapper = AUDIT_WRAPPER.replace("__FUNCTION_NAME__", repr(function))
                updated = code + wrapper
                ast.parse(updated, filename=handler_file)
                contents = updated.encode("utf-8")
            writer.writestr(info, contents)
    # Verify archive and handler source remain readable before altering local Terraform files.
    with zipfile.ZipFile(destination, "r") as test:
        if test.testzip() is not None:
            raise RuntimeError(f"Invalid ZIP generated: {destination}")
        ast.parse(test.read(handler_file).decode("utf-8"), filename=handler_file)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--deploy", action="store_true", help="Deploy patched ZIPs to all four AWS Lambda functions")
    args = parser.parse_args()

    terraform_dir = Path.cwd()
    downloaded_dir = Path(tempfile.gettempdir()) / "ticketdesk-lambda-review"
    if not downloaded_dir.is_dir():
        raise RuntimeError(f"Missing downloaded Lambda ZIP folder: {downloaded_dir}")
    if not (terraform_dir / "ticketdesk-new-lambdas.tf").exists():
        raise RuntimeError("Run this script from the TicketDesk terraform directory.")
    if not os.environ.get("AWS_PROFILE"):
        raise RuntimeError("Set AWS_PROFILE=ticketdesk-new in PowerShell first.")

    with tempfile.TemporaryDirectory(prefix="ticketdesk_lambda_logging_") as staging:
        staged = {}
        for function, (handler_file, output_name) in FUNCTIONS.items():
            original = downloaded_dir / f"{function}.zip"
            if not original.is_file():
                raise RuntimeError(f"Missing downloaded ZIP: {original}")
            print(f"VERIFY  {function} currently deployed code...", flush=True)
            verify_download_is_live(function, original, handler_file[:-3])
            candidate = Path(staging) / output_name
            add_logging(original, candidate, handler_file, function)
            staged[function] = (candidate, terraform_dir / output_name)
            print(f"READY   {function}: detailed structured audit logs added", flush=True)

        # All four artifacts are verified before any local ZIPs are replaced.
        for function, (candidate, target) in staged.items():
            target.write_bytes(candidate.read_bytes())
        print("\nUPDATED: Terraform-managed ZIP files (3) and file-processor logging ZIP (1).")

    if not args.deploy:
        print("No AWS functions were modified. To upload, rerun with --deploy.")
        return

    print("\nDeploying 4 code-only updates; no trigger/IAM/SLA/DB changes...")
    for function, (_, target) in staged.items():
        command = [
            "aws", "lambda", "update-function-code", "--function-name", function,
            "--zip-file", "fileb://" + str(target.resolve()), "--region", REGION,
            "--query", "[FunctionName,LastUpdateStatus]", "--output", "text"
        ]
        # Some Lambda updates are async. Ensure update finished before proceeding.
        completed = subprocess.run(command, text=True)
        if completed.returncode != 0:
            raise RuntimeError(f"Deployment stopped: {function}. Earlier updates may have succeeded.")
        completed = subprocess.run(
            ["aws", "lambda", "wait", "function-updated", "--function-name", function, "--region", REGION],
            text=True
        )
        if completed.returncode != 0:
            raise RuntimeError(f"Deployment wait failed for {function}; inspect its status before continuing.")
        print(f"DEPLOYED {function}", flush=True)

    print("\nSUCCESS: All four Lambda functions now emit TICKETDESK_AUDIT entries on NEW invocations.")
    print("CloudWatch does not retroactively add entries to historical invocations.")


if __name__ == "__main__":
    try:
        main()
    except (RuntimeError, subprocess.CalledProcessError, OSError, zipfile.BadZipFile) as exc:
        print(f"STOP: {exc}", file=sys.stderr)
        sys.exit(1)
