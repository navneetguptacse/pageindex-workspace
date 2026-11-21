from collections.abc import Iterable
from itertools import islice

from app.config import Settings
from app.schemas import ChatMessageInput

Prompt = str | list[dict[str, str]]


def supplied_turns(messages: list[ChatMessageInput]) -> Iterable[tuple[str, str]]:
    for index in range(len(messages) - 1, 0, -1):
        question, answer = messages[index - 1 : index + 1]
        if question.role == "user" and answer.role == "assistant":
            yield question.content, answer.content


def estimated_tokens(text: str) -> int:
    if text.isascii():
        return (len(text) + 2) // 3
    ascii_count = sum(character.isascii() for character in text)
    non_ascii_bytes = len(text.encode()) - ascii_count
    return (ascii_count + 2) // 3 + non_ascii_bytes


def build_prompt(
    question: str,
    recent_turns: Iterable[tuple[str, str]],
    settings: Settings,
    model: str | None = None,
) -> Prompt:
    byte_budget = settings.chat_history_max_bytes
    token_budget = settings.chat_history_token_budgets.get(
        model or settings.chat_model, settings.chat_history_default_tokens
    )
    turns = iter(recent_turns)
    recent = list(islice(turns, settings.chat_history_turns))
    selected: list[tuple[str, str]] = []
    for user_text, assistant_text in recent:
        size = len(user_text.encode()) + len(assistant_text.encode())
        tokens = estimated_tokens(user_text) + estimated_tokens(assistant_text) + 8
        if size > byte_budget or tokens > token_budget:
            break
        selected.append((user_text, assistant_text))
        byte_budget -= size
        token_budget -= tokens

    if not selected:
        return question

    excerpts: list[tuple[str, str]] = []
    for old_question, old_answer in islice(turns, settings.chat_summary_turns):
        excerpt = (
            " ".join(old_question.split())[:120],
            " ".join(old_answer.split())[:180],
        )
        excerpt = (
            f"Earlier question excerpt: {excerpt[0]}",
            f"Earlier answer excerpt: {excerpt[1]}",
        )
        tokens = sum(map(estimated_tokens, excerpt)) + 8
        size = sum(len(part.encode()) for part in excerpt)
        if tokens > token_budget or size > byte_budget:
            break
        excerpts.append(excerpt)
        token_budget -= tokens
        byte_budget -= size

    messages = []
    for past_question, past_answer in reversed(excerpts):
        messages.extend(
            [
                {"role": "user", "content": past_question},
                {"role": "assistant", "content": past_answer},
            ]
        )
    for user_text, assistant_text in reversed(selected):
        messages.extend(
            [
                {"role": "user", "content": user_text},
                {"role": "assistant", "content": assistant_text},
            ]
        )
    messages.append({"role": "user", "content": question})
    return messages
