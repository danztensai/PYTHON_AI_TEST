"""Original in-memory runner (Variant A) for A/B comparison."""

from __future__ import annotations


def run_original(now_hhmm: str) -> dict:
    """
    Execute the original logic for a given HH:MM.
    Returns structured results comparable to the refactored service.
    """
    users = {
        "alice": {"quota": 3, "executed": 0},
        "bob": {"quota": 5, "executed": 0},
    }
    tasks = [
        {"user": "alice", "time": "12:00", "action": "sync", "target": "/data/x"},
        {"user": "bob", "time": "12:00", "action": "backup", "target": "/srv/y"},
        {"user": "alice", "time": "12:00", "action": "delete", "target": "/tmp/z"},
    ]

    events: list[dict] = []
    for task in tasks:
        if task["time"] != now_hhmm:
            continue
        user = task["user"]
        if users[user]["executed"] >= users[user]["quota"]:
            events.append(
                {
                    "user": user,
                    "action": task["action"],
                    "target": task["target"],
                    "status": "quota_exceeded",
                    "message": f"{user} has exceeded quota.",
                }
            )
            continue
        events.append(
            {
                "user": user,
                "action": task["action"],
                "target": task["target"],
                "status": "success",
                "message": f"Executing {task['action']} on {task['target']} for {user}",
            }
        )
        users[user]["executed"] += 1

    return {
        "events": events,
        "executed": {name: data["executed"] for name, data in users.items()},
    }
