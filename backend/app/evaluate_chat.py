import argparse
import getpass
import json
from http.cookiejar import CookieJar
from pathlib import Path
from time import perf_counter
from urllib.request import HTTPCookieProcessor, Request, build_opener


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Evaluate answers and citations against trusted PDF scenarios"
    )
    parser.add_argument("scenarios", type=Path)
    parser.add_argument("--url", default="http://127.0.0.1:8000")
    parser.add_argument("--username")
    parser.add_argument(
        "--live",
        action="store_true",
        help="Run scenarios through configured search and model providers",
    )
    arguments = parser.parse_args()
    scenarios = json.loads(arguments.scenarios.read_text())
    if not isinstance(scenarios, list) or not scenarios:
        parser.error("Provide a non-empty array of scenarios")
    for scenario in scenarios:
        if (
            not isinstance(scenario, dict)
            or not scenario.get("name")
            or not scenario.get("turns")
        ):
            parser.error("Each scenario needs a name and at least one turn")
        if not all(
            isinstance(turn, dict) and turn.get("question")
            for turn in scenario["turns"]
        ):
            parser.error("Each turn needs a question")
    if not arguments.live:
        print(
            f"Validated {len(scenarios)} scenarios with {sum(len(case['turns']) for case in scenarios)} turns."
        )
        return

    opener = build_opener(HTTPCookieProcessor(CookieJar()))
    base = arguments.url.rstrip("/") + "/api/v1"

    def post(route: str, payload: dict) -> dict:
        request = Request(
            base + route,
            data=json.dumps(payload).encode(),
            headers={"Content-Type": "application/json"},
        )
        with opener.open(request, timeout=180) as response:
            return json.load(response)

    if arguments.username:
        post(
            "/workspace/login",
            {"username": arguments.username, "password": getpass.getpass("Password: ")},
        )

    report = []
    for scenario in scenarios:
        session_id = None
        target = {
            key: scenario[key] for key in ("doc_id", "collection_id") if key in scenario
        }
        for turn in scenario["turns"]:
            payload = {"question": turn["question"]}
            payload.update({"session_id": session_id} if session_id else target)
            started = perf_counter()
            response = post("/chat", payload)
            elapsed = perf_counter() - started
            session_id = response["session_id"]
            answer = response["answer"].casefold()
            pages = {
                item["page"]
                for item in response.get("citations") or []
                if "page" in item
            }
            expected_pages = set(turn.get("expected_pages", []))
            report.append(
                {
                    "case": scenario["name"],
                    "question": turn["question"],
                    "answer_match": all(
                        text.casefold() in answer
                        for text in turn.get("expected_text", [])
                    ),
                    "citation_match": expected_pages.issubset(pages),
                    "cited_pages": sorted(pages),
                    "seconds": round(elapsed, 3),
                    "usage": response.get("usage"),
                }
            )
    print(json.dumps(report, indent=2))
    if not all(
        result["answer_match"] and result["citation_match"] for result in report
    ):
        raise SystemExit(1)


if __name__ == "__main__":
    main()
