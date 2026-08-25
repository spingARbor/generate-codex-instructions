def normalize_label(value):
    if not isinstance(value, str):
        raise TypeError("label must be a string")
    normalized = value.strip()
    if not normalized:
        raise ValueError("label must not be empty")
    return normalized
