def normalize_label(value):
    if not isinstance(value, str):
        raise TypeError("label must be a string")
    label = value.strip()
    if not label:
        raise ValueError("label must not be empty")
    return label
