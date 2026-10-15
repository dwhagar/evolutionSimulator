# Labels

How the GitHub labels are used. Kept by the TODO thread.

## Task tags

Every task ID in [TODO.md](../TODO.md) (`AREA.N`, for example `TRAIT.13`) is a label, put on the issues and
pull requests that relate to it. The colour shows the category: each area has its own colour family and the
items of an area are shades of it, darkest for item 1 and lighter up to item 6, then the shades repeat. The
colour is worked out from the tag by [`src/evolution_tools/sync_labels.py`](../src/evolution_tools/sync_labels.py),
so a new tag needs no bookkeeping.

| Area | Colour family | Item 1 to 6 |
|---|---|---|
| `DOCS` | grey | `4c4c4c` to `b2b2b2` |
| `INFRA` | slate | `3d4f5c` to `a3b5c2` |
| `DNA` | green | `227730` to `88dd96` |
| `REPRO` | magenta | `77225b` to `dd88c1` |
| `TRAIT` | orange | `914808` to `f7ae6e` |
| `WORLD` | teal | `1f7a6b` to `85e0d1` |
| `BRAIN` | purple | `4c2673` to `b28cd9` |
| `SENSE` | yellow | `8e780b` to `f4de71` |
| `UX` | lime | `4d7a1f` to `b3e085` |
| `SPECIES` | cyan | `136986` to `79cfec` |
| `STORE` | brown | `6b472e` to `d1ad94` |

A new area is added to `AREAS` and `FAMILIES` in the script (a hue and a saturation, away from red and royal blue)
and to the table in TODO.md. When a new task ID appears in TODO.md, the changelog or the decisions log, run
`python -m evolution_tools.sync_labels --apply` (or `scripts\sync-labels.ps1 --apply`; it needs the `gh` command
logged in to the repository). It creates new labels and recolours only the ones that differ. Without `--apply` it
prints the colours. A test checks the scheme (a family per area, shades that stay one hue, no clash with the two
status colours).

## Status labels

- **`needs-owner`**, bright red (`ff0000`): an owner question about the item is still open. On the issue that holds
  the question, and as `needs-owner` in the TODO.md status. Removed from both when the question is answered (the
  answer is logged in [decisions.md](decisions.md) and the issue is closed or its remaining questions are listed).
- **`in-progress`**, royal blue (`4169e1`): a thread is building the item now. The thread puts it on the item's
  issue or pull request when it starts, and the TODO.md status says "in progress"; it is dropped when the pull
  request merges.
