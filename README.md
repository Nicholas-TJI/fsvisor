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

Requests are retried up to five times with exponential backoff and jitter. If every attempt fails, the error is logged and the call returns an empty result rather than raising, so check for an empty DataFrame when that matters. Logging goes to the `fsvisor` logger unless you pass your own `logger`.

## Development

```
uv sync
uv run pytest
```
