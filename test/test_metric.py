import requests

question_id = 79980456

response = requests.get(
    f"https://api.stackexchange.com/2.3/questions/{question_id}",
    params={"site": "stackoverflow"},
    timeout=30
)

response.raise_for_status()

question = response.json()["items"][0]

metrics = {
    "question_id": question["question_id"],
    "view_count": question["view_count"],
    "answer_count": question["answer_count"],
    "score": question["score"],
}

print(metrics)
