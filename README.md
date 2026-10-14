# fsvisor

A small Python client for the [Formsite API](https://support.formsite.com/hc/en-us/articles/360000288594-API) that pulls form results into labeled pandas DataFrames. It handles pagination, multi-value answers, column labeling, and retries, so a project can go from a form ID to a DataFrame in one call. It was originally written by Chris Metcalf as part of an internal reporting project and extracted here so other Formsite projects can share it, alongside [qbvisor](https://github.com/ChrisEMetcalf/qbvisor) for QuickBase.

Requires Python 3.12 or newer.

## Installation

fsvisor is installed straight from GitHub with [uv](https://docs.astral.sh/uv/). From the root of the project that will use it, add it pinned to a release tag:

```
uv add git+https://github.com/Nicholas-TJI/fsvisor --tag v0.1.0
```

This adds `fsvisor` to your `dependencies` and records the source in `pyproject.toml`, so anyone who clones your project gets the same version from a plain `uv sync`:

```toml
[project]
dependencies = [
    "fsvisor",
]

[tool.uv.sources]
fsvisor = { git = "https://github.com/Nicholas-TJI/fsvisor", tag = "v0.1.0" }
```

To move to a newer release, run the same `uv add` command with the new tag. Pinning a tag matters: without one, uv locks whatever commit was on the default branch when you first added it, and upgrades only happen when someone runs `uv lock --upgrade-package fsvisor`.

If you are changing fsvisor and a project that uses it at the same time, clone both side by side and install fsvisor as an editable path dependency instead, so edits take effect without reinstalling:

```
uv add --editable ../fsvisor
```

## Configuration

The client needs three values from your Formsite account. All three are shown on any form under **Form Settings > Integrations > Formsite API**, which lists the API base URL and lets you generate an access token. The base URL has the form `https://fs22.formsite.com/api/v2/myaccount`, where `fs22.formsite.com` is your realm hostname and `myaccount` is your user ID.

| Constructor argument | Environment variable | Example |
| --- | --- | --- |
| `realm_hostname` | `FORMSITE_REALM_HOSTNAME` | `fs22.formsite.com` |
| `api_key` | `FORMSITE_API_KEY` | `Bearer abc123` (the `Bearer` prefix is added if you leave it off) |
| `user_id` | `FORMSITE_USER_ID` | `myaccount` |

The usual setup is a `.env` file in the root of your project:

```
FORMSITE_REALM_HOSTNAME=fs22.formsite.com
FORMSITE_API_KEY=Bearer abc123
FORMSITE_USER_ID=myaccount
```

The client loads `.env` from the current working directory or the nearest parent directory that has one. Variables already set in the environment win over the file, so a CI system or server can supply real values without editing anything. Add `.env` to your project's `.gitignore`; it holds a live API token.

You can also skip the environment entirely and pass values directly, which is handy for scripts that read credentials from somewhere else:

```python
client = FormSiteClient(
    realm_hostname="fs22.formsite.com",
    api_key="abc123",
    user_id="myaccount",
    load_env=False,
)
```

A missing or malformed value raises `ValueError` when the client is created, not on the first request.

## Usage

```python
from fsvisor import FormSiteClient

client = FormSiteClient()

df = client.get_results_dataframe(
    form_id="abcdefghij",
    results_view=107,
    after_date="2026-10-01",
    results_labels=1,
)
```

`get_results_dataframe` fetches every page of results, joins multi-value answers (such as checkboxes) into `"A; B"` strings, and renames columns from Formsite item IDs to their labels. Its arguments:

| Argument | Meaning |
| --- | --- |
| `form_id` | The form's directory name, the last part of the form's URL. Also shown in the Formsite API settings. |
| `results_view` | Which results view to read. `10` is the built-in view with every item; views you create in Formsite have their own three-digit IDs. |
| `results_labels` | Optional ID of a results labels set, which controls the column names. Leave it out to use the item labels from the form itself. |
| `after_date`, `before_date` | Optional filters, either ISO 8601 UTC (`2026-10-01T00:00:00Z`) or local time (`2026-10-01` or `2026-10-01 08:00:00`). |
| `sort_direction` | `"desc"` (newest first, the default) or `"asc"`. |
| `limit_per_request` | Page size for each API call, default `100`. |

Two lower-level methods are also public: `get_form_results` returns one page of raw results as a list of dicts, and `get_form_metadata` returns a dict mapping item IDs to labels.

### Errors

Failures raise rather than returning empty data, so an empty DataFrame always means the form genuinely had no matching results. Errors that can succeed on a second try (connection drops, timeouts, HTTP 429 rate limits, and 5xx server errors) are retried up to five times with exponential backoff, and the last error is raised if every attempt fails. Errors that will fail the same way every time, such as a 401 for a bad API key or a 404 for an unknown form ID, are raised immediately.

Everything raised is a `requests.exceptions.RequestException`. HTTP errors carry the response, so callers can check the status code:

```python
import requests

try:
    df = client.get_results_dataframe(form_id, results_view=107)
except requests.exceptions.HTTPError as err:
    if err.response.status_code == 401:
        ...  # credentials problem
    raise
```

### Logging

The client logs page fetches, retries, and failures through Python's standard `logging` module, on a logger named `fsvisor`. Configure that logger as you would any other, or pass your own with `FormSiteClient(logger=my_logger)`.

## Development

```
git clone https://github.com/Nicholas-TJI/fsvisor
cd fsvisor
uv sync
uv run pytest
```

To publish a release, bump `version` in `pyproject.toml`, commit, and tag the commit to match (for example `git tag v0.2.0 && git push --tags`) so projects can pin to it.

## License

MIT. See [LICENSE](LICENSE).
