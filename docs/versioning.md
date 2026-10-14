# Versioning

Versions use the format `MAJOR.minor.build`, for example `0.0.23`.

- **build** is the number of commits since the start of the current `MAJOR.minor` line. It is
  derived from git, so every commit increments it automatically.
- **major / minor** change only when the owner says so or when a milestone or goal is set. When
  that happens, update `major`/`minor` in [`version.toml`](../version.toml) and set `base` to the
  commit that starts the new line, which resets the build to 0.

We started at `0.0.0` on commit `c21303d`; the next commit is `0.0.1`.

## Checking the version

```bash
python scripts/version.py
```

The package version (`evolution_simulator.__version__`) is computed by the same code when the
package is installed, so run `pip install -e ".[dev]"` again to refresh it after new commits.

## Caveats

- Clones must have full history (`git clone` default; in CI use `fetch-depth: 0`). Without the
  base commit the build number falls back to 0.
- Squash merges collapse a branch into one commit, so the build advances by one per merge
  instead of one per branch commit. Use merge commits or rebase merges to count every commit.
