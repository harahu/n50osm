from returns.io import IOResult
from returns.unsafe import unsafe_perform_io

from n50.web_io.municipality_metadata import MunicipalityMetadata
from n50.web_io.municipality_metadata import get_municipality_metadata


class TestGetMunicipalityMetadata:
    def test(self) -> None:
        res = get_municipality_metadata(query="Lærdal")
        assert isinstance(res, IOResult)

        meta = unsafe_perform_io(res.unwrap())
        assert isinstance(meta, MunicipalityMetadata)
