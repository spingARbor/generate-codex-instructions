# Label normalization contract

`normalize_label` accepts a string and returns its trimmed form. Empty and
whitespace-only labels must raise `ValueError`; non-string values must keep
raising `TypeError`. The public function name and module path are stable.
