def _find_simple_text_span(content: str, entry_id: int, problem_num: int) -> tuple:
    """
    Find the span (start, end) of the 'text' field value for problem
    `problem_num` in entry with id `entry_id`, handling implicit
    string concatenation.

    olympiads.py stores long string values as:
        'text': 'fragment1... '
                'fragment2... '
                'fragment3...',

    This function locates the opening quote of the first fragment and the
    closing quote of the last fragment, returning absolute byte positions.

    Returns: (span_start, span_end) or (-1, -1)
    """
    # Find the entry by 'id' field
    id_pattern = re.compile(
        r"'id'\s*:\s*" + re.escape(str(entry_id)) + r"\s*(?:[,}])"
    )
    id_match = id_pattern.search(content)
    if not id_match:
        return (-1, -1)

    # Scan backward from id_match to find the opening '{' of this dict
    dict_start = id_match.start()
    while dict_start > 0:
        if content[dict_start] == '{':
            break
        dict_start -= 1
    if content[dict_start] != '{':
        return (-1, -1)

    # Scope the dict (track brace depth for Python dict, NOT LaTeX)
    depth = 0
    dict_end = len(content)
    for i in range(dict_start, len(content)):
        c = content[i]
        if c == '{':
            depth += 1
        elif c == '}':
            depth -= 1
            if depth == 0:
                dict_end = i + 1
                break
    # NOTE: brace depth tracking for DICT SCOPING is safe because we're
    # scanning raw source code and Python dict braces are unambiguous.
    # This is different from tracking braces INSIDE a string value.

    scope = content[dict_start:dict_end]

    # Find 'num': problem_num within this scope
    num_pattern = re.compile(r"'num'\s*:\s*" + re.escape(str(problem_num)) + r"\s*(?:[,}])")
    num_match = num_pattern.search(scope)
    if not num_match:
        return (-1, -1)

    prob_start = num_match.start()

    # Find 'text': after 'num':
    text_key_match = re.search(r"'text'\s*:", scope[prob_start:])
    if not text_key_match:
        return (-1, -1)

    # Start of text value (after 'text': and whitespace)
    val_rel = prob_start + text_key_match.end()
    while val_rel < len(scope) and scope[val_rel] in ' \t\n\r':
        val_rel += 1

    if val_rel >= len(scope) or scope[val_rel] != "'":
        return (-1, -1)

    # Now find the end of the multi-fragment value.
    # We scan character by character within the string value,
    # tracking when we're inside a single-quoted fragment.
    #
    # IMPORTANT: Do NOT track brace depth here — the text value may
    # contain LaTeX with unbalanced braces like \begin{cases}...\end{cases}
    # or single braces. Brace tracking would break.

    pos = val_rel + 1  # skip opening quote of first fragment
    last_close = -1  # position of the closing quote of the last fragment found

    while pos < len(scope):
        ch = scope[pos]

        # Handle escape sequences: skip the escaped char after backslash
        if ch == '\\' and pos + 1 < len(scope):
            pos += 2
            continue

        if ch == "'":
            # Possible closing quote of a fragment
            # Check what follows: whitespace + another ' = continuation
            after = pos + 1
            while after < len(scope) and scope[after] in ' \t\n\r':
                after += 1

            if after < len(scope) and scope[after] == "'":
                # This is the end of a fragment, and there's another fragment
                last_close = pos
                pos = after + 1  # skip opening quote of next fragment
                continue
            else:
                # This is the FINAL closing quote of the last fragment
                last_close = pos
                break

        pos += 1

    if last_close == -1:
        return (-1, -1)

    span_start_abs = dict_start + val_rel
    span_end_abs = dict_start + last_close + 1  # +1 to include the closing quote

    return (span_start_abs, span_end_abs)
