MAX_LEN = 4096


def split_text(text: str) -> list[str]:
    if len(text) <= MAX_LEN:
        return [text]

    paragraphs = text.split("\n\n")
    parts: list[str] = []
    current = ""

    for para in paragraphs:
        if len(para) > MAX_LEN:
            if current:
                parts.append(current)
                current = ""
            for start in range(0, len(para), MAX_LEN):
                parts.append(para[start : start + MAX_LEN])
            continue

        candidate = f"{current}\n\n{para}" if current else para
        if len(candidate) <= MAX_LEN:
            current = candidate
        else:
            parts.append(current)
            current = para

    if current:
        parts.append(current)

    return parts
