"""Safe numeric provider diagnostics, without prompts, answers or reasoning text."""


def response_diagnostics(choice, usage, requested_max_tokens):
    """Distinguish answer truncation from a reported reasoning budget exhaustion."""
    usage = usage if isinstance(usage, dict) else {}
    message = choice.get("message") or {}
    message = message if isinstance(message, dict) else {}
    content = message.get("content")
    details = usage.get("completion_tokens_details") or {}
    details = details if isinstance(details, dict) else {}
    result = {"requested_max_tokens": requested_max_tokens,
              "finish_reason": choice.get("finish_reason") if choice.get("finish_reason") in
              ("length", "stop", "tool_calls", "content_filter") else "unknown",
              "answer_chars": len(content) if isinstance(content, str) else 0}
    for key in ("prompt_tokens", "completion_tokens", "total_tokens"):
        value = usage.get(key)
        if type(value) is int and value >= 0:
            result[key] = value
    reasoning = details.get("reasoning_tokens", usage.get("reasoning_tokens"))
    if type(reasoning) is int and reasoning >= 0:
        result["reasoning_tokens"] = reasoning
    else:
        reasoning = 0
    completion = result.get("completion_tokens", 0)
    result["reasoning_only"] = bool(message.get("reasoning_content") or reasoning) and not (
        isinstance(content, str) and content.strip())
    result["reasoning_dominated"] = bool(completion and reasoning >= completion * 0.8)
    return result
