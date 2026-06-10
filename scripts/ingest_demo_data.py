import json
import os
import ssl
import sys
import urllib.error
import urllib.parse
import urllib.request
from argparse import ArgumentParser
from base64 import b64encode
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from backend.app.demo_data import demo_events
from backend.app.models import IncidentEvent


def build_hec_payload(event: IncidentEvent) -> dict[str, object]:
    return {
        "time": event.timestamp.timestamp(),
        "host": "ops-flight-recorder-demo",
        "source": "ops-flight-recorder",
        "sourcetype": event.evidence.sourcetype,
        "index": event.evidence.index,
        "event": {
            "incident_id": "inc-checkout-payment-2026-06-06",
            "event_id": event.id,
            "evidence_id": event.evidence.id,
            "service": event.service,
            "event_type": event.event_type,
            "severity": event.severity,
            "title": event.title,
            "description": event.description,
            "region": event.region,
            "query": event.evidence.query,
            **event.evidence.fields,
        },
    }


def send_payload(payload: dict[str, object], hec_url: str, token: str) -> None:
    body = json.dumps(payload, separators=(",", ":")).encode("utf-8")
    request = urllib.request.Request(hec_url, data=body, method="POST")
    request.add_header("Authorization", f"Splunk {token}")
    request.add_header("Content-Type", "application/json")
    context = ssl._create_unverified_context()
    with urllib.request.urlopen(request, context=context, timeout=10) as response:
        response.read()


def send_management_event(
    event: IncidentEvent,
    base_url: str,
    username: str,
    password: str,
) -> None:
    event_payload = build_management_event(event)
    query = urllib.parse.urlencode(
        {
            "index": event.evidence.index,
            "source": "ops-flight-recorder",
            "sourcetype": event.evidence.sourcetype,
            "host": "ops-flight-recorder-demo",
        }
    )
    url = f"{base_url.rstrip('/')}/services/receivers/stream?{query}"
    request = urllib.request.Request(
        url,
        data=format_stream_event(event_payload, event.timestamp.timestamp()).encode(
            "utf-8"
        ),
        method="POST",
    )
    credentials = b64encode(f"{username}:{password}".encode("utf-8")).decode("ascii")
    request.add_header("Authorization", f"Basic {credentials}")
    request.add_header("Content-Type", "application/json")
    context = ssl._create_unverified_context()
    with urllib.request.urlopen(request, context=context, timeout=10) as response:
        response.read()


def format_stream_event(payload: dict[str, object], timestamp: float) -> str:
    return f"{timestamp} {json.dumps(payload, separators=(',', ':'))}\n"


def ensure_index(base_url: str, username: str, password: str, index: str) -> None:
    body = urllib.parse.urlencode({"name": index}).encode("utf-8")
    request = urllib.request.Request(
        f"{base_url.rstrip('/')}/services/data/indexes",
        data=body,
        method="POST",
    )
    credentials = b64encode(f"{username}:{password}".encode("utf-8")).decode("ascii")
    request.add_header("Authorization", f"Basic {credentials}")
    request.add_header("Content-Type", "application/x-www-form-urlencoded")
    context = ssl._create_unverified_context()
    try:
        with urllib.request.urlopen(request, context=context, timeout=10) as response:
            response.read()
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        if exc.code == 409 or "already exists" in detail.lower():
            return
        raise


def build_management_event(event: IncidentEvent) -> dict[str, object]:
    return {
        "incident_id": "inc-checkout-payment-2026-06-06",
        "event_id": event.id,
        "evidence_id": event.evidence.id,
        "service": event.service,
        "event_type": event.event_type,
        "severity": event.severity,
        "title": event.title,
        "description": event.description,
        "region": event.region,
        "query": event.evidence.query,
        "time": event.timestamp.isoformat(),
        **event.evidence.fields,
    }


def main() -> None:
    parser = ArgumentParser(description="Emit or send Ops Flight Recorder demo data.")
    parser.add_argument(
        "--send",
        action="store_true",
        help="Send events to Splunk HEC instead of printing JSON lines.",
    )
    parser.add_argument(
        "--send-management",
        action="store_true",
        help="Send events through Splunk management API receivers/simple.",
    )
    args = parser.parse_args()

    hec_url = os.getenv(
        "SPLUNK_HEC_URL",
        "https://127.0.0.1:8088/services/collector",
    )
    hec_token = os.getenv("SPLUNK_HEC_TOKEN")
    splunk_base_url = os.getenv("SPLUNK_BASE_URL", "https://127.0.0.1:8089")
    splunk_username = os.getenv("SPLUNK_USERNAME")
    splunk_password = os.getenv("SPLUNK_PASSWORD")
    splunk_index = os.getenv("SPLUNK_INDEX", "ops_demo")
    if args.send and not hec_token:
        raise SystemExit("SPLUNK_HEC_TOKEN is required when using --send.")
    if args.send_management and (not splunk_username or not splunk_password):
        raise SystemExit(
            "SPLUNK_USERNAME and SPLUNK_PASSWORD are required with --send-management."
        )
    if args.send_management and splunk_username and splunk_password:
        try:
            ensure_index(
                splunk_base_url,
                splunk_username,
                splunk_password,
                splunk_index,
            )
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")
            raise SystemExit(
                f"Failed to create or verify Splunk index {splunk_index}: "
                f"HTTP {exc.code} {detail}"
            ) from exc

    for event in demo_events():
        payload = build_hec_payload(event)
        if args.send and hec_token:
            try:
                send_payload(payload, hec_url, hec_token)
            except urllib.error.HTTPError as exc:
                detail = exc.read().decode("utf-8", errors="replace")
                raise SystemExit(
                    f"Failed to send {event.id} to Splunk HEC: HTTP {exc.code} {detail}"
                ) from exc
            except urllib.error.URLError as exc:
                raise SystemExit(f"Failed to send {event.id} to Splunk HEC: {exc}") from exc
            print(f"sent {event.id}")
        elif args.send_management and splunk_username and splunk_password:
            try:
                send_management_event(
                    event,
                    splunk_base_url,
                    splunk_username,
                    splunk_password,
                )
            except urllib.error.HTTPError as exc:
                detail = exc.read().decode("utf-8", errors="replace")
                raise SystemExit(
                    f"Failed to send {event.id} to Splunk management API: "
                    f"HTTP {exc.code} {detail}"
                ) from exc
            except urllib.error.URLError as exc:
                raise SystemExit(
                    f"Failed to send {event.id} to Splunk management API: {exc}"
                ) from exc
            print(f"sent {event.id}")
        else:
            print(json.dumps(payload, separators=(",", ":")))


if __name__ == "__main__":
    main()
