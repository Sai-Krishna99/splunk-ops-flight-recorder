import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from backend.app.demo_data import demo_events


def main() -> None:
    print("Dry-run Splunk ingest payloads:")
    for event in demo_events():
        print(f"{event.timestamp.isoformat()} {event.service} {event.event_type} {event.evidence.query}")


if __name__ == "__main__":
    main()
