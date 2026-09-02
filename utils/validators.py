import re


def validate_message(content, max_length=2000):
    if not content or not isinstance(content, str):
        return False, "Message is empty"

    content = content.strip()

    if len(content) > max_length:
        return False, f"Message exceeds {max_length} characters"

    return True, content


def sanitize_input(content):
    if not content:
        return ""

    content = content.strip()
    content = re.sub(r"@(everyone|here)", "@\u200b\1", content)
    return content


def extract_mentions(content):
    mention_pattern = r"<@!?\d+>"
    return re.findall(mention_pattern, content)


def remove_mentions(content):
    mention_pattern = r"<@!?\d+>"
    return re.sub(mention_pattern, "", content).strip()


def is_command(content, prefixes):
    if isinstance(prefixes, str):
        prefixes = [prefixes]
    return any(content.startswith(p) for p in prefixes)
