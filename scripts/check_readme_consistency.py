#!/usr/bin/env python3
"""Check that the README matches the code it documents.

Run it as part of the test suite: a documented config variable that no
longer exists, or a module that was renamed, is a documentation bug.

    python3 scripts/check_readme_consistency.py
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "src"))

from chronicler.config import ChroniclerConfig  # noqa: E402

README = (REPO / "README.md").read_text()


def documented_env_vars() -> set[str]:
    return set(re.findall(r"`(CHRONICLER_[A-Z0-9_]+)`", README))


def real_env_vars() -> set[str]:
    """Every field on the config, as its CHRONICLER_-prefixed name."""
    return {f"CHRONICLER_{name.upper()}" for name in ChroniclerConfig.model_fields}


#: Environment variables the CLI reads directly rather than through the
#: settings object.
CLI_ONLY_ENV_VARS = {"CHRONICLER_LOG_LEVEL"}


def documented_modules() -> set[str]:
    return set(re.findall(r"`(chronicler\.[a-z_.]+)`", README))


def real_modules() -> set[str]:
    package = REPO / "src" / "chronicler"
    modules = {"chronicler"}
    for path in package.rglob("*.py"):
        if path.name == "__init__.py":
            # A package directory is itself a module path.
            relative = path.parent.relative_to(package.parent)
            modules.add(".".join(relative.parts))
            continue
        relative = path.relative_to(package.parent).with_suffix("")
        modules.add(".".join(relative.parts))
    return modules


def main() -> int:
    problems: list[str] = []

    documented = documented_env_vars()
    real = real_env_vars() | CLI_ONLY_ENV_VARS
    for missing in sorted(real - documented):
        problems.append(f"config field {missing} is not documented in the README")
    for stale in sorted(documented - real):
        problems.append(f"README documents {stale}, which is not a config field")

    for stale in sorted(documented_modules() - real_modules()):
        problems.append(f"README mentions module {stale}, which does not exist")

    if problems:
        print("README consistency problems:")
        for problem in problems:
            print(f"  - {problem}")
        return 1

    print(f"README is consistent: {len(real)} config fields, {len(real_modules())} modules")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
