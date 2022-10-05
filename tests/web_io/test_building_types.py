from returns.io import IOResult
from returns.unsafe import unsafe_perform_io

from n50.web_io.building_types import load_building_types


class TestLoadBuildingTypes:
    def test(self) -> None:
        res = load_building_types()
        assert isinstance(res, IOResult)

        meta = unsafe_perform_io(res.unwrap())
        assert isinstance(meta, dict)
