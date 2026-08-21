def normalize_label(value):
    if not isinstance(value, str):
        raise TypeError("label must be a string")
    return value.strip()
