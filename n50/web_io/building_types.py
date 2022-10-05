import csv

from typing import Any
from typing import Dict

import attrs
import requests

from requests import HTTPError
from returns.io import IOFailure
from returns.io import IOResultE
from returns.io import IOSuccess

from web_io.common import _safe_get


@attrs.frozen(auto_attribs=True, slots=True)
class BuildingType:
    number: str = attrs.field(validator=attrs.validators.instance_of(str))
    name: str = attrs.field(validator=attrs.validators.instance_of(str))
    building_tag: str = attrs.field(validator=attrs.validators.instance_of(str))
    extra_tag: str = attrs.field(validator=attrs.validators.instance_of(str))
    description: str = attrs.field(validator=attrs.validators.instance_of(str))

    @classmethod
    def from_csv_row(cls, row: Dict[str, Any]) -> "BuildingType":
        # TODO: Handle parsing errors
        return cls(
            number=row["id"],
            name=row["name"],
            building_tag=row["building_tag"],
            extra_tag=row["extra_tag"],
            description=row["description"],
        )

    def osm_tags(self) -> Dict[str, str]:
        tag_string = f"{self.building_tag}+{self.extra_tag}".strip().strip("+")
        osm_tags = {}

        tag_list = tag_string.replace(" ", "").split("+")

        for tag_part in tag_list:
            tag_split = tag_part.split("=")
            osm_tags[tag_split[0]] = tag_split[1]

        return osm_tags


def _get_building_types_response() -> IOResultE[requests.Response]:
    # Could also load from disk
    # file = open("building_types.csv")
    return _safe_get(
        url="https://raw.githubusercontent.com/NKAmapper/building2osm/main/building_types.csv"
    )


def _parse_response(response: requests.Response) -> IOResultE[str]:
    try:
        response.raise_for_status()
    except HTTPError as http_e:
        return IOFailure(http_e)
    return IOSuccess(response.text)


def _get_building_types_content() -> IOResultE[str]:
    response_res = _get_building_types_response()
    return response_res.bind(_parse_response)


def _parse_content(content: str) -> IOResultE[Dict[str, Dict[str, str]]]:
    building_csv = csv.DictReader(
        content.splitlines(),
        fieldnames=["id", "name", "building_tag", "extra_tag", "description"],
        delimiter=";",
    )
    next(building_csv)

    building_tags = {
        bt.number: bt.osm_tags()
        for bt in (BuildingType.from_csv_row(row=row) for row in building_csv)
        # TODO: Only call osm_tags once
        if bt.osm_tags()
    }

    return IOSuccess(building_tags)


def load_building_types() -> IOResultE[Dict[str, Dict[str, str]]]:
    """
    Load conversion CSV table for tagging building types
    Format in CSV: "key=value + key=value + ..."
    """
    content_res = _get_building_types_content()
    building_tags_res = content_res.bind(_parse_content)

    return building_tags_res
