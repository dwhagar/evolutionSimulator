# Labels

How the GitHub labels are used. Kept by the TODO thread.

## Task tags

Every task ID in [TODO.md](../TODO.md) (`AREA.N`, for example `TRAIT.13`) is a label, put on the issues and
pull requests that relate to it. Each tag has its own colour, chosen by rotating through the palette in
[`src/evolution_tools/sync_labels.py`](../src/evolution_tools/sync_labels.py): twelve distinct colours, the next one for each new tag in
the order the tags were first seen, so neighbouring tags never share a colour. A tag keeps its colour for good;
the choices are stored in [`.github/label-colours.json`](../.github/label-colours.json) (`next` is the position in
the rotation, so a new tag continues from there).

| # | Colour | Hex |
|---|---|---|
| 1 | blue | `1d76db` |
| 2 | green | `0e8a16` |
| 3 | yellow | `fbca04` |
| 4 | purple | `5319e7` |
| 5 | orange | `ff7619` |
| 6 | teal | `006b75` |
| 7 | pink | `e99695` |
| 8 | light blue | `bfd4f2` |
| 9 | light green | `c2e0c6` |
| 10 | lavender | `d4c5f9` |
| 11 | peach | `f9d0c4` |
| 12 | brown | `8b6f47` |

When a new task ID appears in TODO.md or the changelog, run `python -m evolution_tools.sync_labels --apply` (it needs the
`gh` command logged in to the repository). It adds the new tags to the file, and creates or recolours the labels.
Without `--apply` it only updates the file. A test checks that every tag in TODO.md has a colour in the file.

## `needs-owner`

Dark red (`b60205`). Marks an issue, and the matching item in TODO.md, that has an owner question still open.
It is removed from both when the question is answered (the answer is logged in
[decisions.md](decisions.md) and the issue is closed or its remaining questions are listed).
