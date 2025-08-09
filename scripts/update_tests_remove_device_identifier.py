#!/usr/bin/env python3
"""
Update test files to remove device_identifier named argument from public API calls.

Targets calls to these functions and removes the named argument `device_identifier=...`:
  - async_setup_synthetic_sensors(
  - async_setup_synthetic_sensors_with_entities(
  - async_setup_synthetic_integration(
  - async_setup_synthetic_integration_with_auto_backing(

The script parses argument lists to safely remove the named argument even when
values contain parentheses, strings, or span multiple lines.

Usage:
  - Dry run (default):
      python scripts/update_tests_remove_device_identifier.py --path ha-synthetic-sensors/tests

  - Apply edits in-place:
      python scripts/update_tests_remove_device_identifier.py --path ha-synthetic-sensors/tests --write
"""

from __future__ import annotations

import argparse
import os
import re
from typing import List, Tuple


FUNCTION_NAMES = [
    "async_setup_synthetic_sensors",
    "async_setup_synthetic_sensors_with_entities",
    "async_setup_synthetic_integration",
    "async_setup_synthetic_integration_with_auto_backing",
]


def find_matching_paren(s: str, start_idx: int) -> int:
    """Given s and index of an opening '(', return index of its matching ')'.

    Handles nested (), [], {} and string literals with simple escaping.
    Raises ValueError if no match found.
    """
    i = start_idx
    if s[i] != "(":
        raise ValueError("find_matching_paren called at non-'(' position")

    depth_stack: List[str] = ["("]
    i += 1
    in_string: str | None = None
    escape = False

    while i < len(s):
        ch = s[i]

        if in_string:
            if escape:
                escape = False
            elif ch == "\\":
                escape = True
            elif ch == in_string:
                in_string = None
        else:
            if ch in ("'", '"'):
                in_string = ch
            elif ch in "([{":
                depth_stack.append(ch)
            elif ch in ")]}":
                if not depth_stack:
                    raise ValueError("Unbalanced closing bracket")
                open_ch = depth_stack.pop()
                pair = {')': '(', ']': '[', '}': '{'}
                if pair[ch] != open_ch:
                    raise ValueError("Mismatched brackets")
                if not depth_stack:
                    # matched the original opening '('
                    return i
        i += 1

    raise ValueError("No matching closing parenthesis found")


def split_top_level_args(arg_text: str) -> List[str]:
    """Split argument list text into top-level args by commas, ignoring nested structures and strings."""
    args: List[str] = []
    current: List[str] = []
    depth_stack: List[str] = []
    in_string: str | None = None
    escape = False

    for ch in arg_text:
        if in_string:
            current.append(ch)
            if escape:
                escape = False
            elif ch == "\\":
                escape = True
            elif ch == in_string:
                in_string = None
        else:
            if ch in ("'", '"'):
                in_string = ch
                current.append(ch)
            elif ch in "([{":
                depth_stack.append(ch)
                current.append(ch)
            elif ch in ")]}":
                if not depth_stack:
                    # allow stray, just append
                    current.append(ch)
                else:
                    open_ch = depth_stack.pop()
                    pair = {')': '(', ']': '[', '}': '{'}
                    if pair[ch] != open_ch:
                        # mismatched, but continue conservatively
                        pass
                    current.append(ch)
            elif ch == "," and not depth_stack:
                args.append("".join(current))
                current = []
            else:
                current.append(ch)

    # last arg
    tail = "".join(current)
    if tail.strip():
        args.append(tail)
    elif tail:  # whitespace only — keep to preserve some formatting
        args.append(tail)
    return args


def normalize_arg(arg: str) -> str:
    # Trim a single trailing comma and outer whitespace
    a = arg.strip()
    if a.endswith(","):
        a = a[:-1].rstrip()
    return a


def rebuild_args(original_args: List[str], kept_args: List[str]) -> str:
    """Rebuild argument string using original multi-line vs single-line style."""
    original_text = ",".join(original_args)
    multiline = "\n" in original_text

    if not kept_args:
        return ""

    if not multiline:
        return ", ".join(a.strip() for a in kept_args)

    # Multiline: try to preserve indentation of the first non-empty argument
    first = original_args[0]
    # Find indentation from the start of the first arg line
    lines = original_text.splitlines()
    indent = ""
    if len(lines) >= 1:
        # detect spaces at start of first arg line
        m = re.match(r"\s*", lines[0])
        indent = m.group(0) if m else ""

    rebuilt_lines = []
    for idx, a in enumerate(kept_args):
        arg_line = a.rstrip()
        # add trailing comma for all but maybe the last — but allow trailing comma
        if idx < len(kept_args) - 1:
            arg_line = f"{arg_line},"
        rebuilt_lines.append(f"{indent}{arg_line}")

    return "\n".join(rebuilt_lines)


def transform_calls_in_text(text: str) -> Tuple[str, int]:
    """Transform text by removing device_identifier named arg from target function calls.

    Returns (new_text, num_replacements)
    """
    num_changes = 0
    i = 0
    while i < len(text):
        # find the next target function occurrence
        next_pos = len(text)
        found_name = None
        for name in FUNCTION_NAMES:
            pos = text.find(name + "(", i)
            if pos != -1 and pos < next_pos:
                next_pos = pos
                found_name = name
        if found_name is None:
            break

        call_start = next_pos + len(found_name)
        if call_start >= len(text) or text[call_start] != "(":
            i = next_pos + 1
            continue

        try:
            close_idx = find_matching_paren(text, call_start)
        except ValueError:
            # can't parse reliably; skip this occurrence
            i = next_pos + 1
            continue

        args_text = text[call_start + 1 : close_idx]
        original_args = split_top_level_args(args_text)
        kept: List[str] = []
        removed_any = False
        for arg in original_args:
            norm = normalize_arg(arg)
            # Strip outer whitespace for detection but keep original for rebuild
            if norm.lstrip().startswith("device_identifier="):
                removed_any = True
                continue
            kept.append(arg)

        if removed_any:
            new_args = rebuild_args(original_args, kept)
            text = text[: call_start + 1] + new_args + text[close_idx:]
            num_changes += 1
            # adjust i to after this call to avoid infinite loop
            i = call_start + 1 + len(new_args) + 1  # plus closing paren
        else:
            i = close_idx + 1

    return text, num_changes


def process_file(path: str, write: bool) -> int:
    with open(path, "r", encoding="utf-8") as f:
        content = f.read()

    new_content, changes = transform_calls_in_text(content)
    if changes and write:
        with open(path, "w", encoding="utf-8") as f:
            f.write(new_content)
    return changes


def iter_python_files(root: str):
    for dirpath, _dirnames, filenames in os.walk(root):
        for fn in filenames:
            if fn.endswith(".py"):
                yield os.path.join(dirpath, fn)


def main() -> None:
    parser = argparse.ArgumentParser(description="Remove device_identifier from test API calls")
    parser.add_argument("--path", required=True, help="Path to tests root (e.g., ha-synthetic-sensors/tests)")
    parser.add_argument("--write", action="store_true", help="Write changes in-place (default is dry-run)")
    args = parser.parse_args()

    total_files = 0
    total_changes = 0
    for file_path in iter_python_files(args.path):
        changes = process_file(file_path, args.write)
        if changes:
            total_files += 1
            total_changes += changes
            print(f"{file_path}: updated {changes} call(s)")

    mode = "WROTE" if args.write else "DRY-RUN"
    print(f"{mode}: {total_changes} call site(s) across {total_files} file(s)")


if __name__ == "__main__":
    main()


