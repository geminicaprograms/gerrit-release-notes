# Gerrit release-notes workflow

A [Claude Code](https://claude.com/claude-code) multi-agent **Workflow** that
drafts the release-notes page for a [Gerrit Code Review](https://www.gerritcodereview.com)
release from git history and `Release-Notes:` commit footers.

- **`.0` mode** (default) — the full `x.y.0` page: highlights, important notes,
  change-list sections, plugins, JGit, dependency bumps, new contributors.
- **`bugfix` mode** — the `### x.y.Z` sections under `## Bugfix releases`, one per
  bugfix tag, written in place into an existing page.

The output is a **draft**. It deliberately over-includes, and classification is
non-deterministic run to run, so a human curation pass is always required.

## Files

| File | Purpose |
|------|---------|
| `gerrit-release-notes.js` | The workflow script |
| `reflow_md.py` | Wraps Markdown prose to a width without breaking links or inline code; the workflow runs it as its last step |
| `reorder_to_match_original.py` | Optional: reorders a generated page to match a hand-authored one, for diffing |

## Prerequisites

- Claude Code with the **Workflow** tool, and access to the Sonnet and Opus models
- `git`, `python3`, `curl` on `PATH`
- Network access to `gerrit-review.googlesource.com` (Change-Id → change number lookups)
- Local clones of
  - `gerrit` (`https://gerrit.googlesource.com/gerrit`) with tags and stable
    branches fetched: `git fetch origin --tags`
  - `homepage` (`https://gerrit.googlesource.com/homepage`), where the output is written

**Cost:** the 3.15.0 run (528 candidate commits, 249 included) took 48 agents,
≈ 2.7M subagent tokens and 24 min wall-clock. Expect the same order of magnitude
for any `.0` release. Bugfix mode is much smaller: one agent per bugfix release,
plus a validation agent each.

## Install

Clone this repo **inside** your Gerrit checkout, and keep it out of `git status`:

```sh
cd <gerrit>
git clone https://github.com/geminicaprograms/gerrit-release-notes \
  .claude/workflows/gerrit-release-notes
echo '.claude/workflows/gerrit-release-notes/' >> .git/info/exclude
echo '.claude/tmp/' >> .git/info/exclude
```

Update later with `git -C .claude/workflows/gerrit-release-notes pull`.

**Why inside the checkout:** Claude Code loads a workflow script only from a
directory the session can access, and it checks the real path. So a symlink
pointing at a clone elsewhere (for example `~/gerrit-release-notes`) is refused
with `scriptPath must be a script path this tool returned, or a file you can
already read`. If you keep the clone elsewhere, add that directory to the
session (`claude --add-dir <dir>` or `/add-dir`) and pass `toolsDir`.

## Run — `x.y.0` release

Start `claude` in the Gerrit checkout and ask in plain words, naming the script
path, for example:

> Run the workflow `.claude/workflows/gerrit-release-notes/gerrit-release-notes.js`
> with args `{"version":"3.15.0","gerritRepo":"/abs/path/gerrit","homepageRepo":"/abs/path/homepage"}`

Before the final tag exists, end the range at the stable branch instead, e.g.
`"tag":"origin/stable-3.15"` (any git ref works).

Defaults derived from `version`: `tag` = `v3.15.0`, `prevVersion` = `3.14`,
`prevBranch` = `origin/stable-3.14`, output = `<homepage>/pages/site/releases/3.15.0-generated.md`.
For a major bump (`4.0.0`) pass `prevVersion` and `prevBranch` explicitly.

Pipeline: Collect → Classify (Sonnet, batches) → Rescue + Recall →
Resolve change numbers + Subprojects (plugins, JGit, deps, community) →
Synthesize (Opus) → Assemble (chunked write) → Reflow. The result includes
`phaseTimes`, and each phase logs a `⏱` line.

## Run — bugfix sections (`x.y.1` … `x.y.N`)

> Run the workflow `.claude/workflows/gerrit-release-notes/gerrit-release-notes.js` with args
> `{"version":"3.15.0","mode":"bugfix","gerritRepo":"…","homepageRepo":"…","outputPath":"<homepage>/pages/site/releases/3.15.md"}`

Bugfix tags `v3.15.1…` are auto-detected (or pass `releases:["3.15.1",…]`). Each
`### x.y.Z` block is replaced **in place** in `outputPath`; the rest of the file
is preserved byte-for-byte and only the new blocks are reflowed.

**Reuse of human-approved notes.** If an approved `### x.y.Z` block already exists,
it is reused verbatim. In `augment` mode, user-facing commits that the block missed
come back as `proposedAdditions` (each with a ready-to-paste `draftedEntry`). They
are logged and returned, never auto-inserted.

| Arg | Default | Meaning |
|-----|---------|---------|
| `reuseApproved` | `true` | `false` = always regenerate |
| `approvedFrom` | `"auto"` | `"auto"` (outputPath, then `<x.y>.md`), `"file:<abs path>"`, or `"gerrit:<change#>"` (a homepage change, fetched over REST; must be **merged**) |
| `allowUnmergedApproved` | `false` | Allow a `gerrit:<n>` source that is not merged yet. Only for a change whose content you trust (see Security) |
| `reuseMode` | `"augment"` | `"augment"` (reuse + propose additions) or `"verbatim"` (reuse as-is) |
| `reconcileRefs` | `true` | After generation, take `[Change N]` numbers for matching entries from the existing block in `outputPath` (reference only, never prose) |

Each bugfix release also gets a **coverage audit** (`Validate` phase): every
non-merge commit in the tag range is marked in, folded or excluded, and genuine
misses are flagged in `validation[]`.

## All args

Paths must be absolute and use only `A-Z a-z 0-9 . _ / -`; git refs use the same
set and may not start with `-`. Anything else stops the run before any agent starts.

| Arg | Default | Notes |
|-----|---------|-------|
| `version` | **required** | `x.y.z`, e.g. `3.15.0` |
| `gerritRepo` | **required** | Absolute path |
| `homepageRepo` | **required** | Absolute path |
| `mode` | `"release"` | `"release"` or `"bugfix"` |
| `tag` | `v<version>` | |
| `prevVersion` | minor − 1 | Required for a major bump |
| `prevBranch` | `origin/stable-<prevVersion>` | |
| `prevReleaseTag` | `v<prevVersion>.0` | JGit delta baseline |
| `stableBranchName` | `stable-<x.y>` | Bugfix mode change-number resolution |
| `outputPath` | `<homepage>/pages/site/releases/<version>-generated.md` | |
| `scratchDir` | `<gerritRepo>/.claude/tmp/relnotes-<version>` | Wiped at the start of each run; last segment must contain `relnotes` and it must not contain any input/output path |
| `toolsDir` | `<gerritRepo>/.claude/workflows/gerrit-release-notes` | Directory containing `reflow_md.py` |
| `batchSize` | `50` | Commits per Classify agent; 90 made single agents take ~22 min |
| `proseWidth` | `80` | Wrap width (release-notes house style ≈ 80, not 72) |
| `sections` | 3.14 taxonomy | Override the change-list section names (see below) |
| `sectionAliases` | — | Map legacy labels onto `sections` |
| `fallbackSection` | `"Bug fixes"` | Where an entry with an unknown section lands |
| `recallPass` | `true` | Second look at excluded commits for wrongly-dropped user-facing changes |
| `community` | `true` | Emit the `## Community` new-contributors section |
| `releases` | auto-detect | Bugfix mode: explicit list of `x.y.Z` |

## Curation rules the workflow encodes

These were reverse-engineered from the hand-curated 3.12–3.14 pages. Change them
in the script prompts if the editorial conventions move.

**Commit range**
- `.0`: `git log --no-merges $(git merge-base <prevBranch> <tag>)..<tag>`.
- Bugfix: successive tags, `v x.y.(Z-1)..v x.y.Z`.
- Dropped as noise: version/rc bumps, "Update git submodules", "Update JGit", and
  any change whose Change-Id is also on `prevBranch` (not version-specific).

**Include / exclude**
- `Release-Notes:` is a starting point only (~75% say `skip`). Judgement is based on
  the actual change: a `skip` can be promoted when user/admin-facing.
- Every commit with a real (non-`skip`) footer is force-included (Rescue step).
- A recall pass re-examines every excluded commit, because promoting a `skip` is
  pure model judgement and the main source of misses.
- Build/tooling/dependency churn is excluded from the change list (deps get their
  own deduped section, keeping only the final version of each artifact).

**Sections (`.0`)** — default, 3.14 convention, in order: Breaking Changes,
Performance Changes, Permissions & Security Changes, New Features, Bug fixes,
Frontend changes, Documentation changes. Empty sections are dropped; headers have
no trailing period; code and config go in backticks. Names drift between releases
(3.13 had "Performance improvements" and "Other Changes"), so override with `sections`.
A new capability is a New Feature even when it's UI-only or relaxes a restriction.
Highlights and sections coexist: a highlighted change is still listed in its
section (a normal `.0` has 25–40 New Features).

**Sections (bugfix)** — `### x.y.Z` → `* <Category>` → 2-space-indented
`* [ref]:` bullets. Categories: Bug Fixes, UI Fixes, Enhancements, plus Security
Fixes, Performance improvements, Documentation changes, Dependency Updates
(bazel/JDK toolchain bumps only), Plugins, JGit changes as needed. Commits fixing
the same `Bug: Issue N` are folded into one entry. Changed plugins are detected
deterministically with `git diff --name-only <prev> <tag> -- plugins/`.

**References**
- `Bug: Issue N` → `[Issue N]` link only; otherwise `[Change N]`. `Google-Bug-Id` is ignored.
- Change numbers are not in git, only Change-Ids. Resolve with
  `GET /changes/?q=change:<Change-Id>+project:gerrit&n=10`; `+project:gerrit` is
  required (without it you get bogus tiny numbers). Reject numbers < 100000.
- Pick by branch, because the same Change-Id has different numbers per branch:
  - `.0`: prefer `master`, else the lowest `stable-*`.
  - Bugfix: prefer `stable-x.y`, else the lowest `stable-*` (the fix was reviewed
    on an older stable branch and merged up), else `master`. Don't filter with
    `branch:stable-x.y`, which returns nothing for merge-up fixes.

**JGit** delta is shown since the previous release tag (`prevReleaseTag`), not the
merge-base. Highlights and Important Notes carry `<!-- TODO: review -->` markers.

## After the run

- Review every `<!-- TODO: review -->` marker and trim the over-inclusive lists.
- Diffing against a hand-authored page:
  `python3 reorder_to_match_original.py <orig.md> <generated.md> <out.md>`.
  Before treating an original-only change number as a miss, check: (1) is its
  Change-Id also on `prevBranch`? (correctly dropped); (2) is the commit outside
  `merge-base..tag`? (out of `.0` scope); (3) does a sibling entry cite the same
  fix under another branch's number? (master vs cherry-pick numbers differ).
- Iterating on a prompt: in the **same** Claude session, re-run with
  `resumeFromRunId:<id>`; only steps whose prompt changed re-run. After a session
  reset, start a fresh run.

## Known issues

- **Writer stall.** The final write is chunked into ~160-line parts
  (`<scratchDir>/_out_NNN.part`, then concatenated) to avoid a model giving up on a
  huge verbatim output. If a part agent stalls anyway, its text is in that agent's
  prompt between `<<<PART_START>>>`/`<<<PART_END>>>` in the run's agent transcript;
  write the missing part yourself and `cat` the parts in order.
- **Non-determinism.** Counts and borderline sectioning vary between runs.
- **Change-number flakiness** in bugfix mode is mitigated by `reconcileRefs` when
  the destination file already has human-verified numbers.

## Security

The workflow starts agents that run shell commands (`git`, `curl`, `python3`) and
read text written by other people: commit messages, plugin logs, and release notes
fetched from Gerrit. A crafted commit message could try to steer an agent
(prompt injection). Mitigations in the script:

- every agent prompt starts with an instruction to treat that text as data, never
  as instructions;
- all args that reach a shell are validated against a metacharacter-free set, and
  bugfix tags reported by an agent are re-validated before use;
- `approvedFrom: "gerrit:<n>"` is not fetched unless the change is merged. A
  separate agent checks the status first with a fixed command that prints only
  the status field, so the change's own text can't influence the decision;
  anything other than `MERGED` is refused (override: `allowUnmergedApproved: true`);
- scratch files live in your checkout (`<gerritRepo>/.claude/tmp/`), not in the
  shared `/tmp`.

These reduce the risk; they don't remove it. Run the workflow in Claude Code's
normal permission mode, **not** with permissions bypassed, and review what the
agents propose to run. The install step adds `.claude/tmp/` to your Gerrit checkout's
`.git/info/exclude` so scratch files never get committed.

## License

Apache License 2.0, see [LICENSE](LICENSE).
