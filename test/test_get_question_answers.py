import json
from datetime import datetime, timezone

import requests


QUESTION_ID = 79980456
API_URL = f"https://api.stackexchange.com/2.3/questions/{QUESTION_ID}/answers"


def to_iso8601(unix_time: int | None) -> str | None:
    if unix_time is None:
        return None
    return datetime.fromtimestamp(unix_time, tz=timezone.utc).isoformat()


def get_question_answers() -> list[dict]:
    response = requests.get(
        API_URL,
        params={
            "site": "stackoverflow",
            "sort": "creation",
            "order": "asc",
            "pagesize": 100,
            "filter": "withbody",
        },
        timeout=30,
    )
    response.raise_for_status()
    payload = response.json()

    if "error_id" in payload:
        raise RuntimeError(
            f"API error {payload['error_id']}: "
            f"{payload.get('error_name')} - {payload.get('error_message')}"
        )

    results = []
    for answer in payload.get("items", []):
        owner = answer.get("owner", {})
        results.append(
            {
                "stackoverflow_answer_id": answer.get("answer_id"),
                "author_user_id": owner.get("user_id"),
                "author_display_name": owner.get("display_name"),
                "is_accepted": answer.get("is_accepted", False),
                "score": answer.get("score", 0),
                "answer_body": answer.get("body"),
                "answer_created_at": to_iso8601(answer.get("creation_date")),
                "last_activity_at": to_iso8601(answer.get("last_activity_date")),
            }
        )

    print(f"Quota remaining: {payload.get('quota_remaining')}")
    return results


if __name__ == "__main__":
    answers = get_question_answers()
    print(json.dumps(answers, ensure_ascii=False, indent=2))
