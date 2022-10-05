from typing import Final

import requests

from returns.io import IOFailure
from returns.io import IOResultE
from returns.io import IOSuccess


HEADER: Final = {"User-Agent": "nkamapper/n50osm"}


def _safe_get(url: str) -> IOResultE[requests.Response]:
    try:
        result = requests.get(url, headers=HEADER)
        return IOSuccess(result)
    except requests.exceptions.RequestException as re:
        return IOFailure(re)
