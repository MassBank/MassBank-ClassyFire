This repository contains Python scripts to query ClassyFire API and to update the ChemOnt classification in MassBank record files. In addition, a sunburst plot can be created. 


## Retry and timeout behaviour

All requests to the ClassyFire API (`utils.request_with_retry`, used by `structure_query`, `get_results` and
`request_by_inchikey.py`) go through a shared `requests.Session` and are retried with exponential backoff plus jitter:

- Retried: HTTP 429, 500, 502, 503, 504, connection errors and timeouts (a numeric `Retry-After` header is honoured).
- Not retried: all other 4xx responses (the request fails immediately).
- Every retry is logged as a warning; a final failure is logged as an error with method, URL, status code,
  number of attempts and a short excerpt of the response, and raises `utils.ClassyFireRequestError`
  (a subclass of `requests.exceptions.RequestException`).
- In `request.py` a chunk that cannot be submitted does not abort the run. It is reported as a GitHub Actions
  warning and its SMILES are written to `results/retry_later.tsv`. The affected records keep having no ChemOnt
  classification and are therefore queried again in the next run.

Configuration via environment variables:

| Variable | Default | Description |
|---|---|---|
| `CLASSYFIRE_URL` | `http://classyfire.wishartlab.com` | Base URL of the ClassyFire API |
| `CLASSYFIRE_MAX_ATTEMPTS` | `5` | Maximum number of attempts per request |
| `CLASSYFIRE_BACKOFF_INITIAL` | `1.0` | Initial backoff in seconds (doubled after each attempt, plus up to this value as jitter) |
| `CLASSYFIRE_BACKOFF_MAX` | `60.0` | Upper bound for a single backoff in seconds |
| `CLASSYFIRE_CONNECT_TIMEOUT` | `5` | Connect timeout in seconds |
| `CLASSYFIRE_READ_TIMEOUT` | `30` | Read timeout in seconds |

HTTP is kept as default because the public ClassyFire API is only documented and used (e.g. by pyclassyfire) via
HTTP and HTTPS support could not be verified. Set `CLASSYFIRE_URL=https://classyfire.wishartlab.com` to use HTTPS.

Run the unit tests with `python -m unittest discover -s tests`.
