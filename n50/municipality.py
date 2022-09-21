import sys
import urllib.error
import urllib.parse
import urllib.request
from typing import Any
from returns.io import IOResult

import requests

import attrs

HEADER = {"User-Agent": "nkamapper/n50osm"}

MUNS_KEY = "kommuner"
MUN_NUMBER_KEY = "kommunenummer"
MUN_NAME_KEY = "kommunenavnNorsk"


@attrs.frozen(auto_attribs=True, slots=True)
class Municipality:
    name: str
    number: str

    @classmethod
    def from_request_result(cls, mun: dict[str, Any]) -> "Municipality":
        return cls(
            name=mun[MUN_NAME_KEY],
            number=mun[MUN_NUMBER_KEY],
        )

    def to_string(self) -> str:
        return f"{self.number} {self.name}"


def get_municipality_name(query: str) -> IOResult[Municipality, str]:
    """Get name and id of municipality from GeoNorge API"""
    if query.isdecimal():
        url = f"https://ws.geonorge.no/kommuneinfo/v1/kommuner/{query}"
    else:
        url = f"https://ws.geonorge.no/kommuneinfo/v1/sok?knavn={urllib.parse.quote(query)}"

    result = requests.get(url, headers=HEADER)
    if result.status_code != 200:
        if result.status_code == 404:
            sys.exit("\tMunicipality '%s' not found\n\n" % query)
        else:
            result.raise_for_status()

    result_json = result.json()

    if query.isdecimal():
        return Municipality.from_request_result(mun=result_json)

    else:
        municipalities = [Municipality.from_request_result(mun=mun) for mun in result_json[MUNS_KEY]]

        if len(municipalities) > 1:
            sys.exit(
                f"\tMore than one municipality found: {', '.join(m.to_string() for m in municipalities)}\n\n"
            )

        elif len(municipalities) == 1:
            return municipalities[0]

        sys.exit(1)


m = get_municipality_name("Lærdal")

print(m.to_string())
