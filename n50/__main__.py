import sys

from cleo.application import Application
from cleo.commands.command import Command


class OsmCommand(Command):
    """
    Extracts N50 topo data from Kartverket and creates an OSM file

    osm
        {municipality : Name of municipality or 4 digit municipality number}
        {category : Data category}
        {--d|debug : Include extra tags and lines for debugging, including original N50 tags.}
        {--t|tag : Include original N50 tags.}
        {--g|geojson : Output raw N50 data in geojson format file.}
        {--s|stream : Load elevation and turn streams to get correct downhill direction of stream (time-consuming).}
        {--e|ele : Load elevation of lakes (time-consuming).}
        {--noname : Do not include SSR names for lakes, islands etc.}
        {--nonve : Do not load lake information from NVE.}
        {--nonode : Do not identify intersections between lines (time-consuming for large municipalities).}
    """

    def handle(self) -> None:
        municipality: str = self.argument('municipality')

        if municipality:
            text = 'Municipality {}'.format(name)
        else:
            text = 'Hello'

        if self.option('debug'):
            text = text.upper()

        self.line(text)


class MergeCommand(Command):
    """
    Merges N50 import file with existing OSM, when importing partitions of a municipality in stages. Also splits import file into smaller files

    merge
        {municipality? : Name of municipality or 4 digit municipality number}
        {category? : Data category}
        {--d|debug : Include extra tags and lines for debugging, including original N50 tags.}
    """

    def handle(self):
        municipality = self.argument('municipality')

        if municipality:
            text = 'Hello {}'.format(name)
        else:
            text = 'Hello'

        if self.option('debug'):
            text = text.upper()

        self.line(text)


application = Application(name="n50", version="0.1.0")
application.add(OsmCommand())
application.add(MergeCommand())


def main() -> int:
    return application.run()


if __name__ == "__main__":
    sys.exit(main())
