from fastapi import HTTPException


def provider_failure(
    name: str, exc: Exception, *, chat: bool = False, checking: bool = False
) -> HTTPException:
    status = getattr(exc, "status_code", None)
    if status == 401:
        detail = f"{name} rejected the API key. Check the key in Account settings."
        return HTTPException(422 if checking else 502, detail)
    if status == 403:
        detail = (
            f"{name} denied access. Check the API key and model permissions in Account settings."
            if chat
            else f"{name} denied access. Check the API key and library permissions in Account settings."
        )
        return HTTPException(422 if checking else 502, detail)
    if chat and status in {400, 404, 422} and checking:
        return HTTPException(
            422,
            f"{name} rejected the test request. Check the model ID, model access, and account billing.",
        )
    if chat and status == 404:
        return HTTPException(
            502,
            f"{name} could not find the selected model. Check the model ID and access in Account settings.",
        )
    if status in {402, 429}:
        return HTTPException(
            429,
            f"{name} reported a usage limit. Check your provider quota and billing.",
        )
    if checking:
        return HTTPException(
            503, f"Could not verify the connection to {name}. Try again shortly."
        )
    return HTTPException(
        502, f"{name} could not complete this request. Try again shortly."
    )


def verify_pageindex(api_key: str) -> None:
    from pageindex import PageIndexClient

    try:
        PageIndexClient(index={"api_key": api_key}).list_documents(limit=1)
    except Exception as exc:
        raise provider_failure("PageIndex", exc, checking=True) from None


CHAT_PROVIDER_NAMES = {
    "openai": "OpenAI",
    "deepseek": "DeepSeek",
    "anthropic": "Anthropic",
    "gemini": "Google Gemini",
}


def chat_provider_failure(
    model: str, exc: Exception, *, checking: bool = False
) -> HTTPException:
    name = CHAT_PROVIDER_NAMES[model.split("/", 1)[0]]
    return provider_failure(name, exc, chat=True, checking=checking)


def verify_chat(model: str, api_key: str) -> None:
    from litellm import completion

    try:
        completion(
            model=model,
            messages=[{"role": "user", "content": "Reply OK."}],
            api_key=api_key,
            max_tokens=32,
            timeout=15,
            num_retries=0,
        )
    except Exception as exc:
        raise chat_provider_failure(model, exc, checking=True) from None
