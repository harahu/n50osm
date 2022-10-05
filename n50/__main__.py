#!/usr/bin/env python3

import sys

from cleo.application import Application
from cleo.commands.command import Command
from returns.io import IOFailure
from returns.io import IOSuccess
from returns.unsafe import unsafe_perform_io

from n50.exceptions import N50Error
from n50.generate import generate_main


class GenerateCommand(Command):
    """
    Extracts N50 topo data from Kartverket and generates an OSM file

    generate
        {municipality : Name of municipality or 4 digit municipality number}
        {category : Data category}
        {--d|debug : Include extra tags and lines for debugging, including original N50 tags.}
        {--t|tag|tags : Include original N50 tags.}
        {--g|geojson|json : Output raw N50 data in geojson format file.}
        {--s|stream|bekk : Load elevation and turn streams to get correct downhill direction of stream (time-consuming).}
        {--e|ele|høyde : Load elevation of lakes (time-consuming).}
        {--noname : Do not include SSR names for lakes, islands etc.}
        {--nonve : Do not load lake information from NVE.}
        {--nonode : Do not identify intersections between lines (time-consuming for large municipalities).}
    """

    def _report_err(self, e: Exception) -> IOSuccess[int]:
        if isinstance(e, N50Error):
            self.line_error(text=e.args[0], style="error")
        else:
            self.line_error(text=str(e), style="error")
        return IOSuccess(1)

    def handle(self) -> int:
        municipality: str = self.argument("municipality")
        category: str = self.argument("category")

        res = generate_main(
            cli=self,
            municipality_query=municipality,
            data_category=category,
            debug=self.option("debug"),
            n50_tags=self.option("tags"),
            json_output=self.option("json"),
            turn_stream=self.option("stream"),
            lake_ele=self.option("ele"),
            no_name=self.option("noname"),
            no_nve=self.option("nonve"),
            no_node=self.option("nonode"),
        )

        print(res)

        if isinstance(res, IOFailure):
            res = res.lash(self._report_err)
        else:
            res = res.map(lambda n: 0)

        return unsafe_perform_io(res.unwrap())


class MergeCommand(Command):
    """
    Merges N50 import file with existing OSM, when importing partitions of a municipality in stages. Also splits import file into smaller files

    merge
        {municipality? : Name of municipality or 4 digit municipality number}
        {category? : Data category}
        {--d|debug : Include extra tags and lines for debugging, including original N50 tags.}
    """

    def handle(self) -> int:
        municipality = self.argument("municipality")

        if municipality:
            text = "Hello {}".format(name)
        else:
            text = "Hello"

        if self.option("debug"):
            text = text.upper()

        self.line(text)
        return 0


application = Application(name="n50", version="0.1.0")
application.add(GenerateCommand())
application.add(MergeCommand())


def main() -> int:
    return application.run()


if __name__ == "__main__":
    sys.exit(main())
