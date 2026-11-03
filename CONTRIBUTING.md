# Contributing to computor-agent

## Development environment

The project uses Python 3.10 or newer; CI runs on Python 3.12. Install the
package with its development dependencies, as described under
"Development installation" in the [README](README.md):

```bash
uv sync --extra dev        # or: pip install -e ".[dev]"
```

The tutor can be run locally without a backend in development mode, see
[docs/development-mode.md](docs/development-mode.md).

## Making a change

1. Branch from `main`.
2. Keep each pull request to one purpose and write a short, imperative commit
   subject that says what changes.
3. Run the same checks as CI before pushing:

   ```bash
   uv run ruff check . --select E9,F63,F7,F82
   uv run pytest
   ```

4. Open a pull request against `main`. Pull requests are squash-merged once
   CI passes and the change has been reviewed.

## Licence

By contributing you agree that your code is licensed under the MIT licence
([LICENSE](LICENSE)) and your documentation under CC BY 4.0
([LICENSE-DOCS](LICENSE-DOCS)).
