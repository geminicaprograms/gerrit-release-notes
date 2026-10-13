#!/usr/bin/env python3
"""Reorder entries within change-list sections of GEN to match ORIG's order.
One-time aid for per-change diffing. Unmatched (gen-only) entries go to section end."""
import re, sys

ORIG, GEN, OUT = sys.argv[1], sys.argv[2], sys.argv[3]
# Union of the taxonomy names used across releases (3.13 used "Performance
# improvements"/"Other Changes"; 3.14 uses "Performance Changes"/"Permissions &
# Security Changes"). Only sections present under the SAME name in both files are
# reordered, so listing all is safe.
TARGETS = ['Breaking Changes', 'New Features', 'Performance improvements',
           'Performance Changes', 'Permissions & Security Changes',
           'Bug fixes', 'Frontend changes', 'Other Changes',
           'Documentation changes']
NUM = re.compile(r'\[(?:Change|Issue) (\d+)\]')
H2 = re.compile(r'^## (.+?)\s*$')
ENTRY = re.compile(r'^\* ')


def split_sections(text):
    """Return (preamble_lines, [(header_name, header_line, body_lines), ...])."""
    lines = text.split('\n')
    pre, secs, i = [], [], 0
    while i < len(lines) and not H2.match(lines[i]):
        pre.append(lines[i]); i += 1
    while i < len(lines):
        m = H2.match(lines[i]); name = m.group(1); hline = lines[i]; i += 1
        body = []
        while i < len(lines) and not H2.match(lines[i]):
            body.append(lines[i]); i += 1
        secs.append([name, hline, body])
    return pre, secs


def split_entries(body):
    """(preamble_lines, [entry_block_lines, ...]) — entry = bullet line + lines up to next bullet."""
    starts = [j for j, l in enumerate(body) if ENTRY.match(l)]
    if not starts:
        return body, []
    pre = body[:starts[0]]
    entries = []
    for k, s in enumerate(starts):
        e = starts[k + 1] if k + 1 < len(starts) else len(body)
        entries.append(body[s:e])
    return pre, entries


def nums(entry_lines):
    return [int(n) for n in NUM.findall('\n'.join(entry_lines))]


# Build ORIG per-section number -> rank (entry index)
_, osecs = split_sections(open(ORIG).read())
orank = {}
for name, _h, body in osecs:
    if name not in TARGETS:
        continue
    _pre, entries = split_entries(body)
    d = {}
    for idx, e in enumerate(entries):
        for n in nums(e):
            d.setdefault(n, idx)  # first occurrence wins
    orank[name] = d

# Reorder GEN
pre, gsecs = split_sections(open(GEN).read())
INF = 10 ** 9
out = list(pre)
moved = {}
for name, hline, body in gsecs:
    if name in TARGETS and name in orank:
        epre, entries = split_entries(body)
        d = orank[name]
        order = []
        for gi, e in enumerate(entries):
            ranks = [d[n] for n in nums(e) if n in d]
            order.append((min(ranks) if ranks else INF, gi))  # stable by gi
        order.sort(key=lambda x: (x[0], x[1]))
        new_body = list(epre) + [ln for _, gi in order for ln in entries[gi]]
        moved[name] = (len(entries), sum(1 for r, _ in order if r == INF))
        out.append(hline); out.extend(new_body)
    else:
        out.append(hline); out.extend(body)

open(OUT, 'w').write('\n'.join(out))
for k, (tot, unmatched) in moved.items():
    print(f'{k}: {tot} entries reordered ({unmatched} gen-only -> end)')
