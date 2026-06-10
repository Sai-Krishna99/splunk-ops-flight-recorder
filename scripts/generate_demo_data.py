import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from backend.app.demo_data import demo_events, demo_incident_summary


def main() -> None:
    payload = {
        "incident": demo_incident_summary().model_dump(mode="json"),
        "events": [event.model_dump(mode="json") for event in demo_events()],
    }
    print(json.dumps(payload, indent=2))


if __name__ == "__main__":
    main()
