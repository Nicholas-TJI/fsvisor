# fsvisor

A small client for the Formsite API that pulls form results into labeled pandas DataFrames. It was extracted from the TJ Roll Up project's `formsite_client.py` (originally written by Chris Metcalf) so other Formsite projects can share it, in the same spirit as `qbvisor` for QuickBase.

## Install

From another uv project:

```
uv add "fsvisor @ git+<repo-url>"
```

Or, while developing side by side, as an editable path dependency:

```
uv add --editable ../fsvisor
```

## Configuration

The client needs three values. Pass them to the constructor, or leave them out and they are read from environment variables. A `.env` file in the working directory (or any parent) is loaded automatically unless you pass `load_env=False`; it never overrides variables that are already set.

| Argument | Environment variable | Example |
| --- | --- | --- |
| `realm_hostname` | `FORMSITE_REALM_HOSTNAME` | `fs22.formsite.com` |
| `api_key` | `FORMSITE_API_KEY` | `Bearer abc123` (the `Bearer` prefix is added if missing) |
| `user_id` | `FORMSITE_USER_ID` | `myaccount` |

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

`get_results_dataframe` pages through every result, flattens multi-value answers into `"A; B"` strings, and renames columns from Formsite item IDs to their labels. The lower-level `get_form_results` (one page of raw results) and `get_form_metadata` (item ID to label map) are also public.

Failures raise rather than returning empty data, so an empty DataFrame always means the form genuinely had no matching results. Errors that can succeed on a second try (connection drops, timeouts, HTTP 429 rate limits, and 5xx server errors) are retried up to five times with exponential backoff and jitter, and the last error is raised if every attempt fails. Errors that will fail the same way every time, such as a 401 for a bad API key or a 404 for an unknown form ID, are raised immediately without retrying. Everything raised is a `requests.exceptions.RequestException`, and HTTP errors carry the response, so callers can inspect `err.response.status_code`:

```python
import requests

try:
    df = client.get_results_dataframe(form_id, results_view=107)
except requests.exceptions.HTTPError as err:
    if err.response.status_code == 401:
        ...  # credentials problem
    raise
```

Logging goes to the `fsvisor` logger unless you pass your own `logger`.

## Development

```
uv sync
uv run pytest
```
