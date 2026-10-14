# Versioning

Versions use the format `MAJOR.minor.build`, for example `0.0.23`.

- **build** is the number of merges into `main` since the start of the current `MAJOR.minor`
  line. It is derived from git (first-parent commits since a base commit), so it increments
  automatically on every merge. Squash merges and merge commits both count once.
- **major / minor** change only when the owner says so or when a milestone or goal is set. When
  that happens, update `major`/`minor` in [`version.toml`](../version.toml) and set `base` to the
  commit that starts the new line, which resets the build to 0.

Lines so far:

| Line | Starts at commit | Set by |
| --- | --- | --- |
| 0.0 | `c21303d` | Project start |
| 0.1 | `9900778` | Owner set milestone 0.1 (data models for DNA and traits) |

The first merge after a line starts is `M.m.1`.

## Checking the version

```bash
python scripts/version.py
```

On a feature branch the script counts the branch's own commits on top of its base, so it only
matches the released build once merged. The package version (`evolution_simulator.__version__`)
is computed by the same code when the package is installed, so run `pip install -e ".[dev]"`
again to refresh it.

## Caveats

- Clones must have full history (`git clone` default; in CI use `fetch-depth: 0`). Without the
  base commit the build number falls back to 0.
- Rebase merges replay every branch commit onto `main`, so each one counts. Prefer squash or
  merge commits to keep it at one per merge.
