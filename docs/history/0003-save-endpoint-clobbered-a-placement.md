# 0003 – A live `POST /api/save` silently overwrote a saved placement

**What:** A test request against the running placement server destroyed an hour
of hand-tuning: `POST /api/save` with `{"name":"try1", ...}` and a 1-part dummy
payload replaced the real 124-part
`hardware/layout_poc/placements/try1.json` (8422 → 486 bytes).

**Why:** `/api/save` is a plain overwrite — that is the intended workflow (save,
tweak, save again), and the name is just a string in the save box. Nothing in the
endpoint, and nothing in the UI, distinguishes "re-save my work" from "write
something else under a name that happens to exist". A *test* therefore had
exactly the same destructive authority as the user's own Save button.

**Outcome:** The file was not recoverable — the placement's `positions` cannot be
derived from the seed, the repository had no committed copy, the container
exposes no block device for the filesystem (`/dev/sdd` is bind-mounted only), and
that filesystem is mounted with `discard`, so the truncated blocks were returned.
The only copy left was the browser tab that made it.

**Status:** Not a bug in the product; a note on how to test and what protects you.

- **Never point a test write at a name that exists.** Use a throwaway name
  (`_selftest`) and delete it afterwards; the endpoint cannot tell your test
  apart from a real save.
- **What actually protects a placement is a commit.** Since
  [0016](0016-placement-ui-decisions.md) saved placements live in the tracked
  `ui/placement/placements/`, but the
  container's copy is not a git repository — the write only reaches git after
  `export.sh` + `git add`/`git commit` on the host. Between Save and commit the
  file has no history, exactly like any other working-tree file.
- **Backup for free:** the browser tab holds the unsaved state; pressing *Save*
  again rewrites the file from it.
