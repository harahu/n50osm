import urllib.parse

from typing import Any
from typing import Final

import attrs
import requests

from requests import HTTPError
from returns.io import IOFailure
from returns.io import IOResultE
from returns.io import IOSuccess
from returns.result import Failure
from returns.result import ResultE
from returns.result import Success

from n50.exceptions import N50Error


HEADER = {"User-Agent": "nkamapper/n50osm"}

MUNICIPALITIES_KEY: Final = "kommuner"
MUNICIPALITY_NUMBER_KEY: Final = "kommunenummer"
MUNICIPALITY_NAME_KEY: Final = "kommunenavnNorsk"


@attrs.frozen(auto_attribs=True, slots=True)
class MunicipalityMetadata:
    name: str = attrs.field(validator=attrs.validators.instance_of(str))
    number: str = attrs.field(validator=attrs.validators.instance_of(str))

    @classmethod
    def from_request_result(cls, mun: dict[str, Any]) -> "MunicipalityMetadata":
        # TODO: Handle parsing errors
        return cls(
            name=mun[MUNICIPALITY_NAME_KEY],
            number=mun[MUNICIPALITY_NUMBER_KEY],
        )

    def to_string(self) -> str:
        return f"{self.number} {self.name}"


def _get_municipality_response_from_number(number: str) -> requests.Response:
    url = f"https://ws.geonorge.no/kommuneinfo/v1/kommuner/{number}"
    return requests.get(url, headers=HEADER)


def _get_municipality_response_from_name(name: str) -> requests.Response:
    url = f"https://ws.geonorge.no/kommuneinfo/v1/sok?knavn={urllib.parse.quote(name)}"
    return requests.get(url, headers=HEADER)


def _get_municipality_response(query: str) -> requests.Response:
    return (
        _get_municipality_response_from_number(number=query)
        if query.isdecimal()
        else _get_municipality_response_from_name(name=query)
    )


def _get_municipality_json(query: str) -> IOResultE[requests.Response]:
    response = _get_municipality_response(query=query)
    try:
        response.raise_for_status()
    except HTTPError as http_e:
        if http_e.response.status_code == 404:
            try:
                raise N50Error(f"Municipality '{query}' not found") from http_e
            except N50Error as n50_e:
                return IOFailure(n50_e)
        return IOFailure(http_e)
    return IOSuccess(response.json())


def _parse_municipalities_json(
    municipalities_json: dict[str, Any]
) -> ResultE[MunicipalityMetadata]:
    municipalities = [
        MunicipalityMetadata.from_request_result(mun=mun)
        for mun in municipalities_json[MUNICIPALITIES_KEY]
    ]

    if len(municipalities) > 1:
        try:
            raise N50Error(
                "More than one municipality found: "
                f"{', '.join(m.to_string() for m in municipalities)}"
            )
        except N50Error as e:
            return Failure(e)

    elif len(municipalities) == 1:
        return Success(municipalities[0])
    else:
        raise AssertionError("This shouldn't happen")


def get_municipality_metadata(query: str) -> IOResultE[MunicipalityMetadata]:
    """Get name and id of municipality from GeoNorge API"""
    json_res = _get_municipality_json(query=query)

    if query.isdecimal():
        return json_res.map(MunicipalityMetadata.from_request_result)
    return json_res.bind_result(_parse_municipalities_json)
