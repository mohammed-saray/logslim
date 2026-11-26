"""Shrink logs while keeping what an AI (or a human) needs to debug."""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import List, Optional

ANSI = re.compile(r"\x1b\[[0-9;?]*[ -/]*[@-~]|\x1b\][^\x07]*\x07")
TIMESTAMP = re.compile(
    r"^\s*(?:\[?\d{4}-\d{2}-\d{2}[T ]\d{2}:\d{2}:\d{2}(?:[.,]\d+)?(?:Z|[+-]\d{2}:?\d{2})?\]?"
    r"|\[?\d{2}:\d{2}:\d{2}(?:[.,]\d+)?\]?"
    r"|[A-Z][a-z]{2} +\d{1,2} \d{2}:\d{2}:\d{2})\s*[-|:]?\s*")
VOLATILE = [
    (re.compile(r"\b[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}\b", re.I), "<uuid>"),
    (re.compile(r"\b0x[0-9a-f]{6,}\b", re.I), "<addr>"),
    (re.compile(r"\b[0-9a-f]{32,64}\b", re.I), "<hash>"),
    (re.compile(r"\b\d{4}-\d{2}-\d{2}[T ]\d{2}:\d{2}:\d{2}(?:[.,]\d+)?(?:Z|[+-]\d{2}:?\d{2})?"), "<time>"),
]
IMPORTANT = re.compile(r"\b(error|err!|fatal|fail(ed|ure)?|exception|traceback|panic|critical|assert|"
                       r"denied|refused|timeout|timed out|cannot|can't|unable|not found|undefined|segfault|"
                       r"warn(ing)?)\b", re.I)
PROGRESS = re.compile(r"(\d{1,3}(\.\d+)?\s?%|[█▓▒░#=>-]{8,}|\b\d+/\d+\b.*(eta|it/s|MB|KB|kB|files))", re.I)
NUMBERS = re.compile(r"\d+(\.\d+)?")

LIB_FRAME = re.compile(
    r"(site-packages|dist-packages|node_modules|node:internal|<frozen |/usr/lib/python|\\lib\\python|"
    r"^\s+at (java|javax|jdk|sun|kotlin|scala|org\.junit|org\.springframework)\.|"
    r"^\s+at (async )?(Module\._compile|Object\.<anonymous> \(node:|processTicksAndRejections)|"
    r"/rustc/|\.cargo/registry|/go/pkg/mod/|runtime/)")
FRAME = re.compile(r'^\s+(File ".*", line \d+|at .+\(.*:\d+(:\d+)?\)|at .+:\d+:\d+|at [\w$.<>]+\(.*\)|'
                   r'\d+: .+ at .+:\d+|[\w./\\-]+\.(go|rs):\d+)')


@dataclass
class Options:
    strip_ansi: bool = True
    strip_timestamps: bool = True
    normalize: bool = True
    dedupe: bool = True
    similar: bool = True
    progress: bool = True
    stacks: bool = True
    keep_frames: int = 2
    similar_min: int = 4
    max_tokens: Optional[int] = None
    context: int = 3


def _template(line: str) -> str:
    return NUMBERS.sub("#", line)


def _norm(line: str) -> str:
    for rx, rep in VOLATILE:
        line = rx.sub(rep, line)
    return line


def clean_lines(text: str, o: Options) -> List[str]:
    out = []
    for raw in text.replace("\r\n", "\n").split("\n"):
        if o.progress and "\r" in raw:
            raw = raw.rsplit("\r", 1)[-1] or raw.split("\r")[-2]  # keep the final state of a \r-redrawn line
        line = ANSI.sub("", raw) if o.strip_ansi else raw
        if o.strip_timestamps:
            line = TIMESTAMP.sub("", line, count=1)
        if o.normalize:
            line = _norm(line)
        out.append(line.rstrip())
    while out and not out[-1]:
        out.pop()
    return out


def collapse_progress(lines: List[str]) -> List[str]:
    out: List[str] = []
    run: List[str] = []

    def flush():
        if len(run) > 2:
            out.append(run[-1] + f"   [progress: {len(run) - 1} earlier updates hidden]")
        else:
            out.extend(run)
        run.clear()

    for line in lines:
        if PROGRESS.search(line) and not IMPORTANT.search(line):
            if run and _template(run[-1])[:12] != _template(line)[:12]:
                flush()
            run.append(line)
        else:
            flush()
            out.append(line)
    flush()
    return out


def collapse_stacks(lines: List[str], keep: int) -> List[str]:
    """Inside stack traces, fold consecutive library frames (keeping `keep` at each end of the trace)."""
    out: List[str] = []
    i = 0
    while i < len(lines):
        if not FRAME.match(lines[i]):
            out.append(lines[i])
            i += 1
            continue
        # gather a whole trace block: frame lines plus their indented source lines
        block = []
        while i < len(lines) and (FRAME.match(lines[i]) or (block and lines[i].startswith("    ") and
                                                             not FRAME.match(lines[i]) and
                                                             FRAME.match(block[-1][0]))):
            if FRAME.match(lines[i]):
                block.append([lines[i]])
            else:
                block[-1].append(lines[i])
            i += 1
        n = len(block)
        result, hidden = [], 0
        for idx, frame in enumerate(block):
            edge = idx < keep or idx >= n - keep
            if LIB_FRAME.search(frame[0]) and not edge:
                hidden += 1
                continue
            if hidden:
                result.append(f"    … {hidden} library frame{'s' if hidden > 1 else ''} hidden …")
                hidden = 0
            result.extend(frame)
        if hidden:
            result.append(f"    … {hidden} library frame{'s' if hidden > 1 else ''} hidden …")
        out.extend(result)
    return out


def collapse_repeats(lines: List[str], similar: bool, similar_min: int) -> List[str]:
    out: List[str] = []
    i = 0
    while i < len(lines):
        j = i + 1
        while j < len(lines) and lines[j] == lines[i]:
            j += 1
        if j - i > 1:
            out.append(f"{lines[i]}   [×{j - i}]")
            i = j
            continue
        if similar and lines[i].strip():
            t = _template(lines[i])
            j = i + 1
            while j < len(lines) and _template(lines[j]) == t and lines[j].strip():
                j += 1
            if j - i >= similar_min:
                out += [lines[i], f"    … {j - i - 2} similar lines …", lines[j - 1]]
                i = j
                continue
        out.append(lines[i])
        i += 1
    return out


def fit_budget(lines: List[str], max_tokens: int, context: int, estimate) -> List[str]:
    """Keep head, tail and windows around important lines until the budget is reached."""
    if estimate("\n".join(lines)) <= max_tokens:
        return lines
    n = len(lines)
    keep = set(range(min(10, n))) | set(range(max(0, n - 30), n))
    for idx, line in enumerate(lines):
        if IMPORTANT.search(line):
            keep.update(range(max(0, idx - context), min(n, idx + context + 1)))

    def render(ks):
        out, last = [], -1
        for k in sorted(ks):
            if k != last + 1:
                out.append(f"… [{k - last - 1} lines omitted] …")
            out.append(lines[k])
            last = k
        if last < n - 1:
            out.append(f"… [{n - 1 - last} lines omitted] …")
        return out

    result = render(keep)
    if estimate("\n".join(result)) > max_tokens:
        # still too big: keep the important lines closest to the end (the final failure matters most)
        imp = [k for k in sorted(keep) if IMPORTANT.search(lines[k])]
        keep = set(range(min(5, n))) | set(range(max(0, n - 15), n))
        for k in reversed(imp):
            trial = keep | set(range(max(0, k - 1), min(n, k + 2)))
            if estimate("\n".join(render(trial))) > max_tokens:
                break
            keep = trial
        result = render(keep)
    if estimate("\n".join(result)) > max_tokens:
        # A huge tail or error line can exceed the budget by itself; keep the latest errors that fit.
        marker = ["[lines omitted]"] if n > 1 and estimate("[lines omitted]") <= max_tokens else []
        result = []
        candidates = [line for line in lines if IMPORTANT.search(line)] or lines[-1:]
        for line in reversed(candidates):
            trial = [line] + result
            if estimate("\n".join(marker + trial)) <= max_tokens:
                result = trial
            elif not result:
                while line:
                    cost = estimate("\n".join(marker + [line]))
                    if cost <= max_tokens:
                        result = [line]
                        break
                    size = min(len(line) - 1, max_tokens * len(line) // cost)
                    line = line[:max(0, size)]
        result = marker + result
    return result


def slim(text: str, o: Optional[Options] = None, estimate=None) -> str:
    from .tokens import estimate as default_estimate
    o = o or Options()
    est = estimate or default_estimate
    lines = clean_lines(text, o)
    if o.progress:
        lines = collapse_progress(lines)
    if o.stacks:
        lines = collapse_stacks(lines, o.keep_frames)
    if o.dedupe:
        lines = collapse_repeats(lines, o.similar, o.similar_min)
    # squeeze blank-line runs
    squeezed: List[str] = []
    for line in lines:
        if line or (squeezed and squeezed[-1]):
            squeezed.append(line)
    if o.max_tokens:
        squeezed = fit_budget(squeezed, o.max_tokens, o.context, est)
    return "\n".join(squeezed)
