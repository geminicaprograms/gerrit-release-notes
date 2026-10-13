#!/usr/bin/env python3
"""Reflow Markdown prose to a fixed width WITHOUT breaking links/code/structure.

Matches the hand-authored Gerrit release-notes style: prose + list-item bodies
are wrapped to --width (default 80); markdown link atoms `[text](url)` and inline
code `` `code` `` are never split (a link longer than the width sits on its own
line); list markers (`*`/`-`/`N.`), indentation, blockquotes, fenced code blocks,
tables, YAML front matter, headers and HTML comments are preserved verbatim.

Usage: reflow_md.py [--width N] FILE   (rewrites FILE in place)
"""
import re
import sys

LINK_RE = re.compile(r'!?\[[^\]]*\]\([^)]*\)')   # [text](url) / ![alt](url)
CODE_RE = re.compile(r'`[^`]*`')                  # `inline code`
LIST_RE = re.compile(r'^(\s*)([*\-+]|\d+[.)])(\s+)(.*)$')
QUOTE_RE = re.compile(r'^(\s*>+\s?)(.*)$')
REF_PREFIX_RE = re.compile(r'(!?\[[^\]]*\]\([^)]*\):)\s*(.*)$')  # bullet content starting "[ref]:" + optional trailing title


def words(text):
    """Split on whitespace that is OUTSIDE link/code spans, so a link (which may
    contain spaces, e.g. `[Issue 123](url)`) plus any glued punctuation (`:`/`,`)
    or inline-code-plus-punctuation stays a single unbreakable word."""
    prot = [False] * len(text)
    for m in list(LINK_RE.finditer(text)) + list(CODE_RE.finditer(text)):
        for k in range(m.start(), m.end()):
            prot[k] = True
    res, cur = [], ''
    for idx, ch in enumerate(text):
        if ch in ' \t' and not prot[idx]:
            if cur:
                res.append(cur); cur = ''
        else:
            cur += ch
    if cur:
        res.append(cur)
    return res


def wrap(text, width, first_prefix, cont_prefix):
    """Greedy-wrap words. A single over-wide word gets its own line."""
    toks = words(text)
    if not toks:
        return [first_prefix.rstrip()]
    lines, cur, prefix = [], '', first_prefix
    for t in toks:
        cand = (prefix + t) if not cur else (cur + ' ' + t)
        if cur and len(cand) > width:
            lines.append(cur)
            cur = cont_prefix + t
        else:
            cur = cand
    if cur:
        lines.append(cur)
    return lines


def _is_struct(ln):
    """A line that is its own block (breaks paragraph runs, copied verbatim)."""
    s = ln.strip()
    return (not s or s.startswith('#') or s.startswith('<!--') or '|' in ln
            or s in ('---', '***', '___') or s.startswith(('Download:', 'Documentation:'))
            or s.startswith('```') or s.startswith('~~~'))


def reflow(src, width=72):
    lines = src.split('\n')
    out, i = [], 0
    # YAML front matter (--- ... ---) at very top, verbatim
    if lines and lines[0].strip() == '---':
        out.append(lines[0]); i = 1
        while i < len(lines) and lines[i].strip() != '---':
            out.append(lines[i]); i += 1
        if i < len(lines):
            out.append(lines[i]); i += 1
    while i < len(lines):
        ln = lines[i]
        stripped = ln.strip()
        # fenced code block: copy verbatim through its closing fence
        if stripped.startswith('```') or stripped.startswith('~~~'):
            out.append(ln); i += 1
            while i < len(lines):
                out.append(lines[i])
                closed = lines[i].strip().startswith(('```', '~~~'))
                i += 1
                if closed:
                    break
            continue
        # blank / structural single lines: verbatim
        if _is_struct(ln):
            out.append(ln); i += 1; continue
        # blockquote run: join consecutive '>' lines, then wrap
        if QUOTE_RE.match(ln):
            pre = QUOTE_RE.match(ln).group(1)
            buf = []
            while i < len(lines) and QUOTE_RE.match(lines[i]):
                buf.append(QUOTE_RE.match(lines[i]).group(2).strip())
                i += 1
            text = ' '.join(x for x in buf if x)
            out.extend(wrap(text, width, pre, re.sub(r'\S', ' ', pre)) if text else [pre.rstrip()])
            continue
        # list item: marker line + its continuation lines (until blank/new item/struct)
        m = LIST_RE.match(ln)
        if m:
            indent, marker, gap, content = m.groups()
            first = f'{indent}{marker}{gap}'
            cont = ' ' * len(first)
            head = content.strip()
            rest = []
            i += 1
            while i < len(lines) and not _is_struct(lines[i]) and not LIST_RE.match(lines[i]) \
                    and not QUOTE_RE.match(lines[i]):
                rest.append(lines[i].strip()); i += 1
            # Release-notes entry shape "* [ref]: Title" — keep the "[ref]:" on its own
            # line and wrap the title/body on continuation lines, so the reference never
            # absorbs the first word(s) of the title. Splits whether the source had the
            # title on the same line as the ref or already on the next line.
            mref = REF_PREFIX_RE.match(head)
            if mref and (mref.group(2) or rest):
                ref, tail = mref.group(1), mref.group(2).strip()
                out.append((first + ref).rstrip())
                title = ' '.join(x for x in ([tail] + rest) if x)
                out.extend(wrap(title, width, cont, cont))
            else:
                out.extend(wrap(' '.join([head] + rest if rest else [head]), width, first, cont))
            continue
        # plain paragraph: join consecutive lines (preserve first line's indent), then wrap
        indent = ln[:len(ln) - len(ln.lstrip())]
        buf = [stripped]
        i += 1
        while i < len(lines) and not _is_struct(lines[i]) and not LIST_RE.match(lines[i]) \
                and not QUOTE_RE.match(lines[i]):
            buf.append(lines[i].strip()); i += 1
        out.extend(wrap(' '.join(x for x in buf if x), width, indent, indent))
    return '\n'.join(out)


def main():
    args = sys.argv[1:]
    width = 80
    if args and args[0] == '--width':
        width = int(args[1]); args = args[2:]
    if not args:
        sys.exit('usage: reflow_md.py [--width N] FILE')
    path = args[0]
    with open(path) as f:
        src = f.read()
    out = reflow(src, width)
    if not out.endswith('\n'):
        out += '\n'
    with open(path, 'w') as f:
        f.write(out)
    print(f'reflowed {path} to width {width}')


if __name__ == '__main__':
    main()
