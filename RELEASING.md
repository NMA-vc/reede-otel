# Releasing reede-otel

Both packages release from one tag. Pushing `vX.Y.Z` runs `.github/workflows/publish.yml`,
which publishes the Python package to PyPI and `@reede/otel` to npm. Each job first checks that
the tag matches its manifest version (`python/pyproject.toml`, `package.json`), then runs the tests.

## One-time setup (owner)

1. **PyPI trusted publisher.** On pypi.org, go to Account settings, then Publishing, then
   "Add a new pending publisher" (the project does not exist yet). Enter:
   - PyPI project name: `reede-otel`
   - Owner: `NMA-vc`
   - Repository name: `reede-otel`
   - Workflow name: `publish.yml`
   - Environment name: leave empty

   No API token is needed. The workflow authenticates with OIDC (`id-token: write`).

2. **npm scope and token.** The scope `@reede` was not found on the npm registry on
   2026-11-21, so it appears unclaimed. Create the `reede` organization on npmjs.com (free for
   public packages), or use an existing one if you already own it. Then create a **Granular
   Access Token** with read and write permission for packages in the `reede` scope and "bypass
   two-factor authentication" enabled. In the GitHub repository (NMA-vc/reede-otel), go to Settings,
   then Secrets and variables, then Actions, and add it as the secret `NPM_TOKEN`.

## Each release

1. Bump the version in **both** `python/pyproject.toml` and `package.json` (currently `0.8.0`),
   and merge that to `main`.
2. Tag the merged commit and push the tag:

   ```bash
   git checkout main && git pull
   git tag v0.8.0
   git push origin v0.8.0
   ```

3. Check the run in the Actions tab. Then confirm the release:

   ```bash
   pip index versions reede-otel
   npm view @reede/otel version
   ```

## If one registry fails

The jobs run independently. If PyPI succeeds and npm fails, re-run only the failed npm job. Do not
re-run the PyPI job unchanged: PyPI rejects a file name that already exists, and the job fails
without publishing anything new. Bump the version to fix a bad release. Do not reuse a version.
