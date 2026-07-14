from datetime import datetime, timedelta, timezone
import json
import requests


API_URL = "https://api.stackexchange.com/2.3/questions"
HOURS_BACK = 24
PAGE_SIZE = 100


def get_latest_questions() -> list[dict]:
    now = datetime.now(timezone.utc)
    from_time = now - timedelta(hours=HOURS_BACK)

    params = {
        "site": "stackoverflow",
        "tagged": "python",
        "sort": "creation",
        "order": "desc",
        "fromdate": int(from_time.timestamp()),
        "todate": int(now.timestamp()),
        "pagesize": PAGE_SIZE,
    }

    response = requests.get(API_URL, params=params, timeout=30)
    response.raise_for_status()
    payload = response.json()

    if "error_id" in payload:
        raise RuntimeError(
            f"Stack Exchange API error {payload['error_id']}: "
            f"{payload.get('error_name')} - {payload.get('error_message')}"
        )

    print(f"API URL: {response.url}")
    print(f"Quota remaining: {payload.get('quota_remaining')}")
    print(f"Questions returned: {len(payload.get('items', []))}\n")
    return payload.get("items", [])


if __name__ == "__main__":
    questions = get_latest_questions()

    with open("tags_questions.json", "w", encoding="utf-8") as f:
        json.dump(questions, f, ensure_ascii=False, indent=2)

    print(f"Saved {len(questions)} questions to tags_questions.json")