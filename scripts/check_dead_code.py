#!/usr/bin/env python3
"""
Script to check for dead code using vulture with different confidence levels.

Usage:
    python scripts/check_dead_code.py [--confidence=60]
"""

import argparse
import subprocess  # nosec B404 - subprocess usage is controlled and safe
import sys
from pathlib import Path


def run_vulture(confidence: int = 60) -> int:
    """Run vulture with the specified confidence level."""
    repo_root = Path(__file__).parent.parent

    cmd = [
        "poetry", "run", "vulture",
        "src/",
        "vulture_whitelist.py",
        f"--min-confidence={confidence}"
    ]

    print(f"Running vulture with {confidence}% confidence...")
    print(f"Command: {' '.join(cmd)}")
    print("-" * 80)

    try:
        result = subprocess.run(  # nosec B603 - command list is controlled, no shell injection
            cmd,
            cwd=repo_root,
            capture_output=False,
            text=True
        )
        return result.returncode
    except subprocess.CalledProcessError as e:
        print(f"Error running vulture: {e}")
        return 1


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="Check for dead code with vulture",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Confidence levels:
  80-100: High confidence dead code (included in pre-commit)
  60-79:  Medium confidence (may include false positives)
  40-59:  Low confidence (many false positives expected)
        """
    )
    parser.add_argument(
        "--confidence",
        type=int,
        default=60,
        help="Minimum confidence level (default: 60)"
    )

    args = parser.parse_args()

    if args.confidence < 1 or args.confidence > 100:
        print("Error: Confidence must be between 1 and 100")
        return 1

    return run_vulture(args.confidence)


if __name__ == "__main__":
    sys.exit(main())