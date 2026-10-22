"""The Chronicler ASCII art and CLI banner."""

CHRONICLER_ASCII = r"""
   _     _ ______ _____ _   _ _______ _     _ 
  | |   | |  ____|_   _| \ | |__   __| |   | |
  | |   | | |__    | | |  \| |  | |  | |   | |
  | |   | |  __|   | | | . ` |  | |  | |   | |
  | |___| | |____ _| |_| |\  |  | |  | |___| |
  \_____|_|______|_____|_| \_|  |_|  \_____/
"""

CHRONICLER_TAGLINE = "The Chronicler — Memory Core of the AI Factory"


def print_banner():
    """Print the ASCII art banner for The Chronicler."""
    print(CHRONICLER_ASCII)
    print(CHRONICLER_TAGLINE)
    print("=" * len(CHRONICLER_TAGLINE))
    print()
    print("Watches the EdgeRecord ledger, extracts failure heuristics")
    print("via local Ollama, and commits hardened rules and lore docs")
    print("back to Git — all headless, all local-first.")
    print()


if __name__ == "__main__":
    print_banner()