#!/usr/bin/env python3
"""
Extract all Flang parse tree node classes from parse-tree.h.

This script extracts:
- struct declarations (direct struct definitions)
- EMPTY_CLASS macro instantiations
- WRAPPER_CLASS macro instantiations
- ENUM_CLASS declarations (enums)
- Classes defined with various boilerplate macros

All extracted names are prefixed with their namespace (Fortran::parser)
and sorted alphabetically.

Usage:
    python extract_flang_nodes.py [options] [file]

Options:
    --classes-only    Output only class/struct names
    --enums-only      Output only enum names
    --all-only        Output combined sorted list (no headers, useful for piping)
    --save, -s        Save output to flang_nodes.txt
    file              Path to parse-tree.h (default: system include path)

Examples:
    python extract_flang_nodes.py                                     # Show all
    python extract_flang_nodes.py --all-only                          # Clean list for iteration
    python extract_flang_nodes.py --classes-only > classes.txt        # Classes only
    python extract_flang_nodes.py --enums-only                        # Enums only
    python extract_flang_nodes.py --save                              # Save to file
    python extract_flang_nodes.py /path/to/parse-tree.h --all-only     # Custom path
"""

import re
import sys
from pathlib import Path


def extract_classes_from_file(filepath):
    """Extract all class/struct/enum names from the parse-tree.h file."""

    with open(filepath, "r") as f:
        content = f.read()

    # Track namespace context
    namespace_stack = []
    in_parser_namespace = False
    parser_depth = 0

    # Results
    classes = set()
    enums = set()

    # Split into lines for processing
    lines = content.split("\n")

    # Multi-line comment tracking
    in_multiline_comment = False

    for line_num, line in enumerate(lines, 1):
        # Handle multi-line comments
        if "/*" in line:
            if "*/" not in line:
                in_multiline_comment = True
        if "*/" in line:
            in_multiline_comment = False
            continue
        if in_multiline_comment:
            continue

        # Skip single-line comments
        if line.strip().startswith("//"):
            continue

        # Remove inline comments
        if "//" in line:
            line = line[: line.index("//")]

        # Skip macro definitions (lines starting with #define or #)
        if line.strip().startswith("#"):
            continue

        # Track namespace
        namespace_match = re.search(r"namespace\s+(\w+)(::\w+)?\s*\{", line)
        if namespace_match:
            ns_name = namespace_match.group(1)
            ns_suffix = namespace_match.group(2) or ""
            namespace_stack.append(ns_name + ns_suffix)
            if "Fortran" in ns_name or any("Fortran" in ns for ns in namespace_stack):
                if "parser" in line or any("parser" in ns for ns in namespace_stack):
                    in_parser_namespace = True
                    parser_depth = len(namespace_stack)
            continue

        if line.strip() == "}" or line.strip().startswith("}"):
            if namespace_stack:
                namespace_stack.pop()
            if in_parser_namespace and len(namespace_stack) < parser_depth:
                in_parser_namespace = False
            continue

        # Pattern 1: EMPTY_CLASS(classname)
        empty_class_match = re.search(r"EMPTY_CLASS\s*\(\s*(\w+)\s*\)", line)
        if empty_class_match:
            classes.add(empty_class_match.group(1))
            continue

        # Pattern 2: WRAPPER_CLASS(classname, type)
        wrapper_class_match = re.search(r"WRAPPER_CLASS\s*\(\s*(\w+)\s*,", line)
        if wrapper_class_match:
            classes.add(wrapper_class_match.group(1))
            continue

        # Pattern 3: struct Name { (definition) - must have body
        # We look for struct declarations followed by { on same line or next lines
        struct_def_match = re.search(r"^\s*struct\s+(\w+)\s*\{", line)
        if struct_def_match:
            class_name = struct_def_match.group(1)
            # Skip forward declarations (no body)
            classes.add(class_name)
            continue

        # Pattern 4: struct Name; (forward declaration) - skip these
        struct_fwd_match = re.search(r"^\s*struct\s+(\w+)\s*;\s*(?://.*)?$", line)
        if struct_fwd_match:
            # Forward declaration, will be defined later
            continue

        # Pattern 5: struct Name { with inheritance
        struct_inherit_match = re.search(r"^\s*struct\s+(\w+)\s*:\s*", line)
        if struct_inherit_match:
            classes.add(struct_inherit_match.group(1))
            continue

        # Pattern 6: ENUM_CLASS(Name, ...) - but skip macro definitions
        enum_class_match = re.search(r"ENUM_CLASS\s*\(\s*(\w+)\s*,", line)
        if enum_class_match:
            enum_name = enum_class_match.group(1)
            # Skip if this looks like a macro parameter name
            if enum_name not in ["Kind", "classname", "Type", "Name", "Value"]:
                enums.add(enum_name)
            continue

        # Pattern 7: Using aliases for classes
        using_match = re.search(r"^\s*using\s+(\w+)\s*=\s*", line)
        if using_match:
            # These are type aliases, not new classes
            pass

    return classes, enums


def extract_using_macros(content):
    """Extract classes defined via macro usage patterns."""
    classes = set()

    # TUPLE_CLASS_BOILERPLATE(classname)
    tuple_matches = re.findall(r"TUPLE_CLASS_BOILERPLATE\s*\(\s*(\w+)\s*\)", content)
    classes.update(m for m in tuple_matches if m != "classname")

    # UNION_CLASS_BOILERPLATE(classname)
    union_matches = re.findall(r"UNION_CLASS_BOILERPLATE\s*\(\s*(\w+)\s*\)", content)
    classes.update(m for m in union_matches if m != "classname")

    # BOILERPLATE(classname) - but only when used in struct context
    boilerplate_matches = re.findall(r"BOILERPLATE\s*\(\s*(\w+)\s*\)", content)
    classes.update(m for m in boilerplate_matches if m != "classname")

    # INHERITED_TUPLE_CLASS_BOILERPLATE(derived, base)
    inherited_matches = re.findall(
        r"INHERITED_TUPLE_CLASS_BOILERPLATE\s*\(\s*(\w+)\s*,", content
    )
    classes.update(m for m in inherited_matches if m != "classname")

    return classes


def main():
    import argparse

    parser = argparse.ArgumentParser(
        description="Extract Flang parse tree node classes from parse-tree.h"
    )
    parser.add_argument(
        "--classes-only", action="store_true", help="Output only class/struct names"
    )
    parser.add_argument(
        "--enums-only", action="store_true", help="Output only enum names"
    )
    parser.add_argument(
        "--all-only",
        action="store_true",
        help="Output only the combined sorted list (no headers)",
    )
    parser.add_argument(
        "--save",
        "-s",
        action="store_true",
        help="Save output to file (stored in flang_nodes.txt)",
    )
    parser.add_argument("file", nargs="?", help="Path to parse-tree.h")
    args = parser.parse_args()

    # Determine output destination
    output_file = None
    if args.save:
        output_file = open("flang_nodes.txt", "w")
    import_stdout = sys.stdout
    sys.stdout = output_file if output_file else import_stdout

    # Find the file
    if args.file:
        filepath = Path(args.file)
    else:
        possible_paths = [
            Path(
                "/usr/lib/llvm-22/include/flang/Parser/parse-tree.h"
            ),  # Common system include path on Linux
        ]

        filepath = None
        for path in possible_paths:
            if path.exists():
                filepath = path
                break

    if not filepath or not filepath.exists():
        print("Error: Could not find flang/parse-tree.h", file=sys.stderr)
        sys.exit(1)

    if not args.all_only and not args.classes_only and not args.enums_only:
        print(f"Reading from: {filepath}")

    # Extract from file
    with open(filepath, "r") as f:
        content = f.read()

    # Get classes
    classes, enums = extract_classes_from_file(filepath)
    macro_classes = extract_using_macros(content)

    # Combine all classes
    all_classes = classes | macro_classes

    # Filter out false positives (macro parameter names and std types)
    false_positives = {"classname", "class", "Type", "Name", "Value", "Kind"}
    all_classes = {
        c
        for c in all_classes
        if not c.startswith("std::") and len(c) > 1 and c not in false_positives
    }
    enums = {e for e in enums if len(e) > 1 and e not in false_positives}

    # Prefix with namespace
    namespaced_classes = sorted([f"Fortran::parser::{c}" for c in all_classes])
    namespaced_enums = sorted([f"Fortran::parser::{e}" for e in enums])
    all_names = sorted(namespaced_classes + namespaced_enums)

    # Output based on options
    if args.all_only:
        for name in all_names:
            print(name)
    elif args.classes_only:
        print(f"\n=== Found {len(namespaced_classes)} Classes/Structs ===\n")
        for name in namespaced_classes:
            print(name)
    elif args.enums_only:
        print(f"\n=== Found {len(namespaced_enums)} Enums ===\n")
        for name in namespaced_enums:
            print(name)
    else:
        # Default: show everything
        print(f"\n=== Found {len(namespaced_classes)} Classes/Structs ===\n")
        for name in namespaced_classes:
            print(name)

        print(f"\n=== Found {len(namespaced_enums)} Enums ===\n")
        for name in namespaced_enums:
            print(name)

        print(f"\n=== All {len(all_names)} Names (Classes + Enums) Sorted ===\n")
        for name in all_names:
            print(name)

    if output_file:
        output_file.close()
        sys.stdout = import_stdout
        print(f"Output written to flang_nodes.txt")


if __name__ == "__main__":
    main()
