import os
import json
import time
import random
import logging
import requests
from requests.adapters import HTTPAdapter
from rdkit import Chem
from rdkit import RDLogger

# Suppress RDKit warnings globally
RDLogger.DisableLog('rdApp.*')

logger = logging.getLogger("classyfire")

# HTTPS is not used by default: the public ClassyFire API is only documented and used
# (e.g. by pyclassyfire) via HTTP and HTTPS support could not be verified. Set
# CLASSYFIRE_URL=https://classyfire.wishartlab.com to switch once HTTPS is confirmed.
url = os.environ.get("CLASSYFIRE_URL", "http://classyfire.wishartlab.com").rstrip("/")

# Retry / timeout configuration (overridable via environment variables)
MAX_ATTEMPTS = int(os.environ.get("CLASSYFIRE_MAX_ATTEMPTS", "5"))
BACKOFF_INITIAL = float(os.environ.get("CLASSYFIRE_BACKOFF_INITIAL", "1.0"))
BACKOFF_MAX = float(os.environ.get("CLASSYFIRE_BACKOFF_MAX", "60.0"))
TIMEOUT = (
    float(os.environ.get("CLASSYFIRE_CONNECT_TIMEOUT", "5")),
    float(os.environ.get("CLASSYFIRE_READ_TIMEOUT", "30")),
)
RETRY_STATUS_CODES = frozenset({429, 500, 502, 503, 504})

# Retries are handled in request_with_retry (also for POST), so the adapter itself does not retry.
session = requests.Session()
session.mount("http://", HTTPAdapter(max_retries=0))
session.mount("https://", HTTPAdapter(max_retries=0))


class ClassyFireRequestError(requests.exceptions.RequestException):
    """Raised when a ClassyFire request finally failed (after all retries or on a non-retryable status)."""

    def __init__(self, message, url=None, status_code=None, attempts=0, response=None):
        super().__init__(message, response=response)
        self.url = url
        self.status_code = status_code
        self.attempts = attempts


def _response_snippet(response, limit=200):
    try:
        text = response.text or ""
    except Exception:
        return ""
    text = " ".join(text.split())
    return text[:limit] + ("..." if len(text) > limit else "")


def _backoff_delay(attempt, backoff_initial, backoff_max, response=None):
    """Exponential backoff with jitter; honours a numeric Retry-After header (capped by backoff_max)."""
    delay = min(backoff_max, backoff_initial * (2 ** (attempt - 1)))
    delay += random.uniform(0, backoff_initial)
    if response is not None:
        retry_after = response.headers.get("Retry-After")
        if retry_after and retry_after.strip().isdigit():
            delay = max(delay, float(retry_after))
    return min(delay, backoff_max)


def request_with_retry(method, request_url, *, max_attempts=None, backoff_initial=None, backoff_max=None,
                       timeout=None, allowed_statuses=(), http_session=None, **kwargs):
    """Send an HTTP request and retry on 429/5xx, connection errors and timeouts.

    Returns the response for 2xx status codes and for status codes listed in ``allowed_statuses``.
    Raises ClassyFireRequestError otherwise: immediately for other 4xx codes, after ``max_attempts``
    attempts for retryable failures.
    """
    max_attempts = max(1, MAX_ATTEMPTS if max_attempts is None else max_attempts)
    backoff_initial = BACKOFF_INITIAL if backoff_initial is None else backoff_initial
    backoff_max = BACKOFF_MAX if backoff_max is None else backoff_max
    timeout = TIMEOUT if timeout is None else timeout
    http_session = session if http_session is None else http_session

    for attempt in range(1, max_attempts + 1):
        response = None
        try:
            response = http_session.request(method, request_url, timeout=timeout, **kwargs)
        except (requests.exceptions.ConnectionError, requests.exceptions.Timeout) as e:
            reason = f"{type(e).__name__}: {e}"
        else:
            if response.ok or response.status_code in allowed_statuses:
                return response
            reason = f"HTTP {response.status_code}"
            if response.status_code not in RETRY_STATUS_CODES:
                message = (f"{method} {request_url} failed with non-retryable {reason} "
                           f"(attempt {attempt}/{max_attempts}): {_response_snippet(response)}")
                logger.error(message)
                raise ClassyFireRequestError(message, url=request_url, status_code=response.status_code,
                                             attempts=attempt, response=response)

        if attempt == max_attempts:
            status_code = response.status_code if response is not None else None
            snippet = f": {_response_snippet(response)}" if response is not None else ""
            message = f"{method} {request_url} failed after {attempt} attempts, last error {reason}{snippet}"
            logger.error(message)
            raise ClassyFireRequestError(message, url=request_url, status_code=status_code,
                                         attempts=attempt, response=response)

        delay = _backoff_delay(attempt, backoff_initial, backoff_max, response)
        logger.warning("%s %s failed with %s (attempt %d/%d), retrying in %.1fs",
                       method, request_url, reason, attempt, max_attempts, delay)
        time.sleep(delay)

def smiles_to_canonical_smiles(smiles):
    mol = Chem.MolFromSmiles(smiles)
    canonical_smiles = Chem.MolToSmiles(mol, canonical=True)

    return canonical_smiles


def inchi_to_canonical_smiles(inchi):
    mol = Chem.MolFromInchi(inchi)
    smiles = Chem.MolToSmiles(mol, canonical=True)

    return smiles


def smiles_to_inchi_key(smiles):
    mol = Chem.MolFromSmiles(smiles)
    inchi_key = Chem.InchiToInchiKey(Chem.MolToInchi(mol))

    return inchi_key


def structure_query(compound, label='IPB-Halle-ClassyFire'):   
    payload = {
        "label": label,
        "query_input": compound,
        "query_type": "STRUCTURE"
    }
    headers = {"Content-Type": "application/json"}
    r = request_with_retry("POST", f"{url}/queries.json", data=json.dumps(payload), headers=headers)
    return r.json()['id']


def get_results(query_id, return_format="json"):  
    r = request_with_retry("GET", f"{url}/queries/{query_id}.{return_format}",
                           headers={"Content-Type": f"application/{return_format}"})
    return r.text


def list_files_recursive(path):
    files = list()
    for entry in os.listdir(path):
        if entry.startswith('.'):
            continue
        full_path = os.path.join(path, entry)
        if os.path.isdir(full_path):
            files.extend(list_files_recursive(full_path))
        elif 'MSBNK-' in full_path and full_path.endswith('.txt'):
                files.append(full_path)
    return files
