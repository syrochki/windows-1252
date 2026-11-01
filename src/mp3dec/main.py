import argparse
from pathlib import Path


def repair_name(name: str) -> tuple[str | None, str | None]:
    """Attempt to repair a name corrupted by encoding mismatches.

    The function converts text from Windows-1252 to Windows-1251 when the
    input contains characters that may indicate mojibake.

    Args:
        name: The original file or directory name.

    Returns:
        A tuple containing the repaired name and None on success, or None
        and an explanation when the name cannot be safely converted.
    """
    if "‹" in name or "›" in name:
        name.replace("‹", "Р").replace("›", "р")

    if not any(0x00C0 <= ord(char) <= 0x00FF for char in name):
        return None, "no likely mojibake markers"

    try:
        repaired = name.encode("cp1252").decode("cp1251")
    except (UnicodeEncodeError, UnicodeDecodeError):
        return None, "cannot safely convert CP1252 text to CP1251"

    if not any("\u0400" <= char <= "\u04ff" for char in repaired):
        return None, "conversion did not produce Cyrillic"

    if repaired in {"", ".", ".."} or "/" in repaired or "\0" in repaired:
        return None, "converted name is not a valid path component"

    return repaired, None


def collect_items(root: Path, kind: str, recursive: bool) -> list[Path]:
    """Collect files and directories matching the requested target type.

    Args:
        root: Directory from which to collect items.
        kind: Item type to collect: "files", "dirs", or "both".
        recursive: Whether to search through nested directories.

    Returns:
        Paths sorted deepest-first so child paths are processed before
        their parent directories.
    """
    iterator = root.rglob("*") if recursive else root.iterdir()
    items = [p for p in iterator if p.is_file() or p.is_dir()]

    if kind == "files":
        items = [p for p in items if p.is_file()]
    elif kind == "dirs":
        items = [p for p in items if p.is_dir()]

    # Deepest-first keeps paths valid while child directories are renamed.
    return sorted(
        items,
        key=lambda p: (len(p.parts), 0 if p.is_file() else 1),
        reverse=True,
    )


def process(root: Path, kind: str, recursive: bool, apply: bool) -> None:
    """Preview or perform renames for the selected files and directories.

    Each item's name is passed to repair_name(). Potential renames are
    checked for destination-name collisions before being previewed or applied.

    Args:
        root: Root directory to process.
        kind: Item type to process: "files", "dirs", or "both".
        recursive: Whether to include nested directories.
        apply: If True, perform renames; otherwise, only preview them.
    """
    items = collect_items(root, kind, recursive)
    changed = skipped = errors = 0

    print(f"Mode: {'APPLY' if apply else 'PREVIEW'}")
    print(f"Root: {root}")
    print(f"Target: {kind}; recursive: {recursive}")
    print(f"Items found: {len(items)}\n")

    for source in items:
        repaired, reason = repair_name(source.name)
        if repaired is None or repaired == source.name:
            if reason and reason != "no likely mojibake markers":
                print(f"SKIP   {source}: {reason}")
                skipped += 1
            continue

        destination = source.with_name(repaired)

        # Case-folded collision detection is useful on common macOS volumes.
        siblings = {child.name.casefold() for child in source.parent.iterdir()}
        if repaired.casefold() in siblings and repaired.casefold() != source.name.casefold():
            print(f"SKIP   {source} -> {destination}: destination already exists")
            skipped += 1
            continue

        if not apply:
            print(f"PREVIEW {source} -> {destination}")
            changed += 1
            continue

        try:
            source.rename(destination)
            print(f"RENAMED {source} -> {destination}")
            changed += 1
        except OSError as exc:
            print(f"ERROR  {source}: {exc}")
            errors += 1

    print("\nSummary")
    print(f"  {'Renamed' if apply else 'Would rename'}: {changed}")
    print(f"  Skipped: {skipped}")
    print(f"  Errors: {errors}")


def main() -> None:
    """Parse CLI arguments, validate the root directory, and run processing."""
    parser = argparse.ArgumentParser(
        description="Repair CP1252/CP1251 mojibake in file and directory names."
    )
    parser.add_argument("directory", type=Path, help="Root directory to process")
    parser.add_argument(
        "--target",
        choices=("both", "files", "dirs"),
        default="both",
        help="Rename files, directories, or both (default: both)",
    )
    parser.add_argument(
        "--no-recursive",
        action="store_true",
        help="Process only immediate children of the root directory",
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Actually rename items (default: preview only)",
    )
    args = parser.parse_args()

    root = args.directory.expanduser().resolve()
    if not root.is_dir():
        parser.error(f"Directory does not exist: {root}")

    process(root, args.target, not args.no_recursive, args.apply)


if __name__ == "__main__":
    main()