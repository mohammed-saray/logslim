"""logslim command-line interface."""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

from . import __version__
from .core import Options, slim
from .tokens import estimate, method


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="logslim", description="Shrink logs and stack traces before pasting "
                                 "them into an AI chat. Reads files or stdin, writes to stdout.")
    ap.add_argument("files", nargs="*", help="log files (default: stdin)")
    ap.add_argument("-t", "--max-tokens", type=int, help="hard budget: keep head, tail and context around errors")
    ap.add_argument("-C", "--context", type=int, default=3, help="lines kept around each error with --max-tokens")
    ap.add_argument("--frames", type=int, default=2, help="library frames kept at each end of a stack trace")
    ap.add_argument("--keep-timestamps", action="store_true")
    ap.add_argument("--keep-ansi", action="store_true")
    ap.add_argument("--no-normalize", action="store_true", help="don't replace uuids/hashes/addresses")
    ap.add_argument("--no-similar", action="store_true", help="only fold exact duplicate lines")
    ap.add_argument("--no-stacks", action="store_true", help="don't fold library stack frames")
    ap.add_argument("-p", "--prompt", nargs="?", const="Here is the relevant log output. Find the root cause "
                    "and suggest a fix.", help="prepend a question for the AI (default prompt if no text)")
    ap.add_argument("-q", "--quiet", action="store_true", help="no stats on stderr")
    ap.add_argument("--version", action="version", version=f"logslim {__version__}")
    a = ap.parse_args(argv)
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            try:
                stream.reconfigure(encoding="utf-8")
            except Exception:
                pass

    if not a.files and sys.stdin.isatty():
        ap.print_help()
        return 2
    try:
        if a.files:
            text = "\n".join(Path(f).read_text(encoding="utf-8", errors="replace") for f in a.files)
        else:
            text = sys.stdin.buffer.read().decode("utf-8", errors="replace")
    except OSError as exc:
        message = str(exc).replace("\r", " ").replace("\n", " ")
        print(f"logslim: {message}", file=sys.stderr)
        return 1
    o = Options(strip_ansi=not a.keep_ansi, strip_timestamps=not a.keep_timestamps, normalize=not a.no_normalize,
                similar=not a.no_similar, stacks=not a.no_stacks, keep_frames=a.frames,
                max_tokens=a.max_tokens, context=a.context)
    out = slim(text, o)
    if a.prompt:
        out = f"{a.prompt}\n\n```text\n{out}\n```"
    sys.stdout.write(out + "\n")
    if not a.quiet:
        before, after = estimate(text), estimate(out)
        saved = 100 * (1 - after / before) if before else 0
        print(f"logslim: {before:,} → {after:,} tokens ({saved:.0f}% smaller, {method()})", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
