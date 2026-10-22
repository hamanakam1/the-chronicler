"""The Chronicler ASCII art - West Coast Lowrider edition."""

CHRONICLER_ASCII = r"""
         _          _ _     _ _         
        | |__   ___| | |__ (_) |_ _   _ 
        | '_ \ / _ \ | '_ \| | __| | | |
        | | | |  __/ | | | | | |_| |_| |
        |_| |_|\___|_|_| |_|\__|\__, |
                                |___/ 
"""

CHRONICLER_TAGLINE = "The Chronicler — Memory Core of the AI Factory"

# High-resolution Los Angeles Lowrider ASCII Art
# Capturing the classic lowrider aesthetic: hydraulics, spinner rims,
# custom paint, and the cruising vibe

LOWRIDER_ART = r"""
                                ____________________
                           ____/                    \______
                      ____/                            \______
                 /                                     \____
                |   ____________         [] _________    |
               |  |          |____________|         |   |
               |  |__________|            |_________|   |
               |=========================================|
               |   O                                    O  |
              |                                          |
              |                                          |
              ||=____________________________=|__________|
               ...........                          ...........
               .         .                          .         .
               .  ::     .                          .  ::     .
               . :::  :  .                          . :::  :  .
               . :OOOOO  .                          . :OOOOO  .
               .  OOOOO  .                          .  OOOOO  .
               .  OOOOO: .                          .  OOOOO: .
               .  :  ::: .                          .  :  ::: .
               .     ::  .                          .     ::  .
               .         .                          .         .
               '''''''''''                          '''''''''''
      ==================================================================


                                         _     _
                                        | |   | |
                                        | |   | |
                                        | |   | |
                                _   _ _   _| |__ | |__   ___  _ __   ___  _ __
                               | | | | | | | '_ \| '_ \ / _ \| '_ \ / _ \| '__|
                               | |_| | |_| | | | | | | |  _/| | | |  _                                      _       _
                                \___/ \___/|_| |_|_| |_| |_| |_| |_| |                                     | |     | |
                                                                                                           | |     | |
                                                                                                   _   _  | |     | |  _   _
                                                                                                  | | | | | |     | | | | | |
                                                                                                  | |_| | | |___  | |_| |_| |
                                                                                                   \___/  \____/  \___/ \___/




"""

CHRONICLER_STYLE_NOTE = r"""
  _          _ _     _ _         
 | |__   ___| | |__ (_) |_ _   _ 
 | '_ \ / _ \ | '_ \| | __| | | |
 | | | |  __/ | | | | | |_| |_| |
 |_| |_|\___|_|_| |_|\__|\__, |
                              |___/ 
"""

LOWRIDER_DETAIL_NOTE = """
Lowrider aesthetics: hydraulics, custom paint, wire wheels,
spinner rims, and the cruising lifestyle. A tribute to LA car
culture and the lowrider tradition.
"""

BANNER_SUMMARY = (
    "Watches the EdgeRecord ledger, extracts failure heuristics\n"
    "via local Ollama, and commits hardened rules and lore docs\n"
    "back to Git — all headless, all local-first."
)


def render_banner() -> str:
    """Return the full ASCII banner as a single string."""
    return "\n".join(
        [
            CHRONICLER_ASCII.strip("\n"),
            CHRONICLER_TAGLINE,
            "=" * len(CHRONICLER_TAGLINE),
            "",
            LOWRIDER_ART.strip("\n"),
            "",
            CHRONICLER_STYLE_NOTE.strip("\n"),
            LOWRIDER_DETAIL_NOTE.strip("\n"),
            "",
            BANNER_SUMMARY,
        ]
    )


def print_banner(stream=None) -> None:
    """Print the ASCII art banner for The Chronicler with Lowrider vibe.

    The banner goes to stderr by default so that stdout stays machine
    readable: ``chronicler run --once | jq`` keeps working even though the
    wordmark is on screen.
    """
    import sys

    target = stream if stream is not None else sys.stderr
    print(render_banner(), file=target)


if __name__ == "__main__":
    print_banner()
