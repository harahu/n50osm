#!/usr/bin/env python3
# -*- coding: utf8


import urllib.request, urllib.parse, urllib.error
import zipfile
from io import BytesIO, TextIOWrapper
import json
import csv
import copy
import sys
import time
import math
from xml.etree import ElementTree as ET
import utm


version = "0.7.2"

header = {"User-Agent": "nkamapper/n50osm"}

coordinate_decimals = 7

island_size = 100000  # Minimum square meters for place=island vs place=islet

lake_ele_size = 2000  # Minimum square meters for fetching elevation

data_categories = [
    "AdministrativeOmrader",
    "Arealdekke",
    "BygningerOgAnlegg",
    "Hoyde",
    "Restriksjonsomrader",
    "Samferdsel",
    "Stedsnavn",
]

avoid_objects = [  # Object types to exclude from output
    "ÅpentOmråde",
    "Tregruppe",  # Arealdekke
    "GangSykkelveg",
    "VegSenterlinje",
    "Vegsperring",  # Samferdsel
    "Forsenkningskurve",
    "Hjelpekurve",
    "Høydekurve",  # Hoyde
    "PresentasjonTekst",  # Stedsnavn
]

auxiliary_objects = [
    "Arealbrukgrense",
    "Dataavgrensning",
    "FiktivDelelinje",
    "InnsjøElvSperre",
    "InnsjøInnsjøSperre",
    "ElvBekkKant",
    "Havflate",
    "Innsjøkant",
    "InnsjøkantRegulert",
    "FerskvannTørrfallkant",
]

avoid_tags = [  # N50 properties to exclude from output (unless debug)
    "oppdateringsdato",
    "datafangstdato",
    "målemetode",
    "nøyaktighet",
]


osm_tags = {
    # Arealdekke
    "Alpinbakke": {"landuse": "winter_sports", "piste:type": "downhill", "area": "yes"},
    "BymessigBebyggelse": {
        "landuse": "retail"
    },  #'landuse': 'residential', 'residential': 'urban' },
    "DyrketMark": {"landuse": "farmland"},
    "ElvBekk": {"waterway": "stream"},
    "FerskvannTørrfall": {"waterway": "riverbank", "intermittent": "yes"},
    "Foss": {"waterway": "waterfall"},
    "Golfbane": {"leisure": "golf_course"},
    "Gravplass": {"landuse": "cemetery"},
    "HavElvSperre": {"natural": "coastline"},
    "HavInnsjøSperre": {"natural": "coastline"},
    "Hyttefelt": {"landuse": "residential", "residential": "cabin"},
    "Industriområde": {"landuse": "industrial"},
    "Innsjø": {"natural": "water"},
    "InnsjøRegulert": {"natural": "water", "water": "reservoir"},
    "Kystkontur": {"natural": "coastline"},
    "Lufthavn": {"aeroway": "aerodrome"},
    "Myr": {"natural": "wetland", "wetland": "bog"},
    "Park": {"leisure": "park"},
    "Rullebane": {"aeroway": "runway"},
    "Skjær": {"seamark:type": "rock"},
    "Skog": {"natural": "wood"},
    "Skytefelt": {"leisure": "pitch", "sport": "shooting"},
    "SnøIsbre": {"natural": "glacier"},
    "SportIdrettPlass": {"leisure": "pitch"},
    "Steinbrudd": {"landuse": "quarry"},
    "Steintipp": {"landuse": "landfill"},
    "Tettbebyggelse": {"landuse": "residential"},
    # Samferdsel
    "Barmarksløype": {"highway": "track"},
    "Traktorveg": {"highway": "track"},
    "Sti": {"highway": "path"},
    # Hoyde
    "Terrengpunkt": {"natural": "hill"},
    "TrigonometriskPunkt": {"natural": "hill"},
    # Restriksjonsomrader
    "Naturvernområde": {"boundary": "protected_area"},
    "Allmenning": {"boundary": "protected_area", "protect_class": "27"},  # Public land
    # BygningerOgAnlegg
    "Bygning": {"building": "yes"},
    "Campingplass": {"tourism": "camp_site"},
    "Dam": {"waterway": "dam"},
    "Flytebrygge": {"man_made": "pier", "floating": "yes"},
    "Gruve": {"man_made": "adit"},  # Could be shaft
    "Hoppbakke": {"piste:type": "ski_jump"},
    "KaiBrygge": {"man_made": "quay"},
    "Ledning": {"power": "line"},
    "LuftledningLH": {"power": "line"},
    "Lysløype": {"highway": "track", "lit": "yes", "trailblazed": "yes"},
    "MastTele": {"man_made": "mast", "tower:type": "communication"},
    "Molo": {"man_made": "breakwater"},
    "Navigasjonsinstallasjon": {"man_made": "lighthouse"},  # Only lighthouses, it seems
    "Parkeringsområde": {"amenity": "parking"},
    "Pir": {"man_made": "pier"},
    "Reingjerde": {"barrier": "fence"},
    "Rørgate": {"man_made": "pipeline"},  # Also "tømmerrenne"
    "Skitrekk": {"aerialway": "drag_lift"},  # Could be other aerialway values
    "Skytebaneinnretning": {"leisure": "pitch", "sport": "shooting"},
    "Tank": {"man_made": "tank"},
    "Taubane": {
        "aerialway": "cable_car"
    },  # Could be other aerial values, e.g. gondola, goods
    "Tårn": {"man_made": "tower"},  # Any massive or substantial tower
    "Vindkraftverk": {
        "power": "generator",
        "generator:source": "wind",
        "generator:type": "horizontal_axis",
    },
}


# OSM tagging; first special cases


def tag_object(feature_type, geometry_type, properties, feature):
    tags = {}
    missing_tags = set()

    # First special object cases

    if feature_type == "ElvBekk":
        if geometry_type == "område":
            tags["waterway"] = "riverbank"
        elif "vannBredde" in properties and properties["vannBredde"] > "2":  # >3 meter
            tags["waterway"] = "river"
        else:
            tags["waterway"] = "stream"

    elif (
        feature_type == "Skytefelt" and data_category == "Restriksjonsomrader"
    ):  # Eception to Arealdekke
        tags["landuse"] = "military"

    elif feature_type == "Bygning":
        if "bygningstype" in properties:
            if properties["bygningstype"] == "956":  # Turisthytte
                if "betjeningsgrad" in properties:
                    if properties["betjeningsgrad"] == "B":  # Betjent
                        tags["tourism"] = "alpine_hut"
                    elif properties["betjeningsgrad"] == "S":  # Selvbetjent
                        tags["tourism"] = "wilderness_hut"
                    elif properties["betjeningsgrad"] in [
                        "U",
                        "D",
                        "R",
                    ]:  # Ubetjent, dagstur, rastebu
                        tags["amenity"] = "shelter"
                        tags["shelter_type"] = "basic_hut"
                    else:
                        tags["amenity"] = "shelter"
                        tags["shelter_type"] = "lean_to"
                if "hytteeier" in properties:
                    if properties["hytteeier"] == "1":
                        tags["operator"] = "DNT"
                    elif properties["hytteeier"] == "3":
                        tags["operator"] = "Fjellstyre"
                    elif properties["hytteeier"] == "4":
                        tags["operator"] = "Statskog"

            elif properties["bygningstype"] in building_tags:
                for key, value in iter(
                    building_tags[properties["bygningstype"]].items()
                ):
                    if (
                        geometry_type == "område" or key != "building"
                    ):  # or len(building_tags[ properties['bygningstype'] ]) > 1:
                        tags[key] = value

        if geometry_type != "posisjon" and "building" not in tags:
            tags["building"] = "yes"  # No building tag for single nodes

    elif feature_type == "Lufthavn":
        if "lufthavntype" in properties and properties["lufthavntype"] == "H":
            tags["aeroway"] = "heliport"
        else:
            tags["aeroway"] = "aerodrome"
            if "trafikktype" in properties:
                if properties["trafikktype"] == "I":
                    tags["aeroway:type"] = "international"
                elif properties["trafikktype"] == "N":
                    tags["aeroway:type"] = "regional"
                elif properties["trafikktype"] == "A":
                    tags["aeroway:type"] = "airfield"
        if "iataKode" in properties and properties["iataKode"] != "XXX":
            tags["iata"] = properties["iataKode"]
        if "icaoKode" in properties and properties["icaoKode"] != "XXXX":
            tags["icao"] = properties["icaoKode"]

    elif geometry_type == "område" and feature_type == "SportIdrettPlass":
        if len(feature["coordinates"]) > 1:
            tags["leisure"] = "track"
            tags["area"] = "yes"
        else:
            tags["leisure"] = "pitch"

    # Then conversion dict

    elif feature_type in osm_tags:
        tags.update(osm_tags[feature_type])

    # Collect set of remaining object types not handled

    elif feature_type not in auxiliary_objects:
        missing_tags.add(feature_type)

    # Additional tagging based on object properties from GML

    if "høyde" in properties:
        tags["ele"] = properties["høyde"]
    if "lavesteRegulerteVannstand" in properties:
        tags["ele:min"] = properties["lavesteRegulerteVannstand"]
    if "vatnLøpenummer" in properties:
        tags["ref:nve:vann"] = properties["vatnLøpenummer"]

    if "navn" in properties:
        tags["name"] = properties["navn"]
    if "fulltekst" in properties:
        tags["name"] = properties["fulltekst"]
    if "stedsnummer" in properties:
        tags["ssr:stedsnr"] = properties["stedsnummer"]
    # 	if "skriftkode" in properties:
    # 		tags['SKRIFTKODE'] = properties['skriftkode']

    if "merking" in properties and properties["merking"] == "JA":
        tags["trailblazed"] = "yes"

    if "verneform" in properties:
        if properties["verneform"] in ["NP", "NPS"]:
            tags["boundary"] = "national_park"
        elif properties["verneform"] in ["LVO", "NM"]:
            tags["boundary"] = "protected_area"
        else:
            tags["leisure"] = "nature_reserve"

    if "lengde" in properties and feature_type == "Hoppbakke":
        tags["ref"] = "K" + properties["lengde"]

    return (tags, missing_tags)


# Output message


def message(output_text):
    sys.stdout.write(output_text)
    sys.stdout.flush()


# Format time


def timeformat(sec):
    if sec > 3600:
        return "%i:%02i:%02i hours" % (sec / 3600, (sec % 3600) / 60, sec % 60)
    elif sec > 60:
        return "%i:%02i minutes" % (sec / 60, sec % 60)
    else:
        return "%i seconds" % sec


# Calculate coordinate area of polygon in square meters
# Simple conversion to planar projection, works for small areas
# < 0: Clockwise
# > 0: Counter-clockwise
# = 0: Polygon not closed


def polygon_area(polygon):
    if polygon[0] == polygon[-1]:
        lat_dist = math.pi * 6371009.0 / 180.0

        coord = []
        for node in polygon:
            y = node[1] * lat_dist
            x = node[0] * lat_dist * math.cos(math.radians(node[1]))
            coord.append((x, y))

        area = 0.0
        for i in range(len(coord) - 1):
            area += (coord[i + 1][1] - coord[i][1]) * (
                coord[i + 1][0] + coord[i][0]
            )  # (x2-x1)(y2+y1)

        return int(area / 2.0)
    else:
        return 0


# Calculate coordinate area of multipolygon, i.e. excluding inner polygons


def multipolygon_area(multipolygon):
    if (
        type(multipolygon) is list
        and len(multipolygon) > 0
        and type(multipolygon[0]) is list
        and multipolygon[0][0] == multipolygon[0][-1]
    ):
        area = polygon_area(multipolygon[0])
        for patch in multipolygon[1:]:
            inner_area = polygon_area(patch)
            if inner_area:
                area -= inner_area
            else:
                return None
        return area

    else:
        return None


# Calculate centroid of polygon
# Source: https://en.wikipedia.org/wiki/Centroid#Of_a_polygon


def polygon_centroid(polygon):
    if polygon[0] == polygon[-1]:
        x = 0
        y = 0
        det = 0

        for i in range(len(polygon) - 1):
            d = polygon[i][0] * polygon[i + 1][1] - polygon[i + 1][0] * polygon[i][1]
            det += d
            x += (polygon[i][0] + polygon[i + 1][0]) * d  # (x1 + x2) (x1*y2 - x2*y1)
            y += (polygon[i][1] + polygon[i + 1][1]) * d  # (y1 + y2) (x1*y2 - x2*y1)

        return (x / (3.0 * det), y / (3.0 * det))

    else:
        return None


# Tests whether point (x,y) is inside a polygon
# Ray tracing method


def inside_polygon(point, polygon):
    if polygon[0] == polygon[-1]:
        x, y = point
        n = len(polygon)
        inside = False

        p1x, p1y = polygon[0]
        for i in range(n):
            p2x, p2y = polygon[i]
            if y > min(p1y, p2y):
                if y <= max(p1y, p2y):
                    if x <= max(p1x, p2x):
                        if p1y != p2y:
                            xints = (y - p1y) * (p2x - p1x) / (p2y - p1y) + p1x
                        if p1x == p2x or x <= xints:
                            inside = not inside
            p1x, p1y = p2x, p2y

        return inside

    else:
        return None


# Test whether point (x,y) is inside a multipolygon, i.e. not inside inner polygons


def inside_multipolygon(point, multipolygon):
    if (
        type(multipolygon) is list
        and len(multipolygon) > 0
        and type(multipolygon[0]) is list
        and multipolygon[0][0] == multipolygon[0][-1]
    ):
        inside = inside_polygon(point, multipolygon[0])
        if inside:
            for patch in multipolygon[1:]:
                inside = inside and not inside_polygon(point, patch)
                if not inside:
                    break

        return inside

    else:
        return None


# Calculate new node with given distance offset in meters
# Works over short distances


def coordinate_offset(node, distance):
    m = 1 / ((math.pi / 180.0) * 6378137.0)  # Degrees per meter

    latitude = node[1] + (distance * m)
    longitude = node[0] + (distance * m) / math.cos(math.radians(node[1]))

    return (longitude, latitude)


# Identify bounds of line coordinates
# Returns lower left and upper right corners of square bounds + extra perimeter (in meters)


def get_bbox(coordinates, perimeter):
    if type(coordinates) is tuple:
        patch = [coordinates]
    elif type(coordinates[0]) is tuple:
        patch = coordinates
    else:
        patch = coordinates[0]

    min_node = list(patch[0])
    max_node = copy.deepcopy(min_node)

    for node in patch:
        for i in [0, 1]:
            min_node[i] = min(min_node[i], node[i])
            max_node[i] = max(max_node[i], node[i])

    if perimeter > 0:
        min_node = coordinate_offset(min_node, -perimeter)
        max_node = coordinate_offset(max_node, +perimeter)

    return [min_node, max_node]


# Create feature with one point


def create_point(node, gml_id, note):
    if debug:
        entry = {
            "object": "Debug",
            "type": "Point",
            "coordinates": node,
            "members": [],
            "tags": {},
            "extras": {"objekttype": "Debug", "note": note},
        }
        if gml_id:
            entry["gml_id"] = gml_id

        features.append(entry)


# Get list of coordinates from GML
# Each point is a tuple of (lon, lat), corresponding to GeoJSON format x,y


def parse_coordinates(coord_text):
    global gml_id

    parse_count = 0
    split_coord = coord_text.split(" ")
    coordinates = []
    for i in range(0, len(split_coord) - 1, 2):
        x = float(split_coord[i])
        y = float(split_coord[i + 1])
        [lat, lon] = utm.UtmToLatLon(x, y, 33, "N")
        node = (round(lon, coordinate_decimals), round(lat, coordinate_decimals))
        parse_count += 1
        if not coordinates or node != coordinates[-1] or json_output:
            coordinates.append(node)
        else:
            # 			message ("\t*** DELETED DUPLICATE NODE: %s %s\n" % (node, gml_id))
            create_point(node, gml_id, "deleted duplicate")

    # Remove single outlayer node

    if not json_output:
        i = 0
        while i < len(coordinates):
            if i > 1 and coordinates[i] == coordinates[i - 2]:
                # 				message ("\t*** DELETED ARTEFACT NODE: %s %s\n" % (coordinates[ i - 1 ], gml_id))
                create_point(
                    copy.deepcopy(coordinates[i - 1]), gml_id, "deleted artefact"
                )
                coordinates.pop(i)
                coordinates.pop(i - 1)
                i -= 1
            else:
                i += 1

        if (
            len(coordinates) > 2
            and coordinates[0] == coordinates[-1]
            and coordinates[1] == coordinates[-2]
        ):
            # 			message ("\t*** DELETED ARTEFACT NODE: %s %s\n" % (coordinates[ 0 ], gml_id))
            coordinates = coordinates[1:-1]

    if len(coordinates) == 1 and parse_count > 1:
        message("\t*** SHORT WAY %s\n" % gml_id)

    return coordinates


# Get name or id of municipality from GeoNorge api


def get_municipality_name(query):
    if query.isdigit():
        url = "https://ws.geonorge.no/kommuneinfo/v1/kommuner/" + query
    else:
        url = "https://ws.geonorge.no/kommuneinfo/v1/sok?knavn=" + urllib.parse.quote(
            query
        )

    request = urllib.request.Request(url, headers=header)

    try:
        file = urllib.request.urlopen(request)
    except urllib.error.HTTPError as e:
        if e.code == 404:  # Not found
            sys.exit("\tMunicipality '%s' not found\n\n" % query)
        else:
            raise

    if query.isdigit():
        result = json.load(file)
        file.close()
        municipality_name = result["kommunenavnNorsk"]
        return (query, municipality_name)

    else:
        result = json.load(file)
        file.close()
        if result["antallTreff"] == 1:
            municipality_id = result["kommuner"][0]["kommunenummer"]
            municipality_name = result["kommuner"][0]["kommunenavnNorsk"]
            return (municipality_id, municipality_name)
        else:
            municipalities = []
            for municipality in result["kommuner"]:
                municipalities.append(
                    municipality["kommunenummer"]
                    + " "
                    + municipalities["kommunenavnNorsk"]
                )
            sys.exit(
                "\tMore than one municipality found: %s\n\n" % ", ".join(municipalities)
            )


# Load conversion CSV table for tagging building types
# Format in CSV: "key=value + key=value + ..."


def load_building_types():
    # 	file = open("building_types.csv")
    url = "https://raw.githubusercontent.com/NKAmapper/building2osm/main/building_types.csv"
    request = urllib.request.Request(url, headers=header)
    file = urllib.request.urlopen(request)

    building_csv = csv.DictReader(
        TextIOWrapper(file, "utf-8"),
        fieldnames=["id", "name", "building_tag", "extra_tag"],
        delimiter=";",
    )
    next(building_csv)

    for row in building_csv:
        tag_string = (row["building_tag"] + "+" + row["extra_tag"]).strip().strip("+")

        if tag_string:
            osm_tag = {}
            tag_list = tag_string.replace(" ", "").split("+")

            for tag_part in tag_list:
                tag_split = tag_part.split("=")
                osm_tag[tag_split[0]] = tag_split[1]

            building_tags[row["id"]] = osm_tag

    file.close()


# Compute length based on coordinates (not in meters)


def simple_length(coord):
    length = 0
    for i in range(len(coord) - 2):
        length += (coord[i + 1][0] - coord[i][0]) ** 2 + (
            (coord[i + 1][1] - coord[i][1]) ** 2
        ) * 0.5

    return length


# Split patch if self-intersecting or touching polygon


def split_patch(coordinates):
    for i in range(1, len(coordinates) - 1):
        first = coordinates.index(coordinates[i])
        if first < i:
            result1 = split_patch(coordinates[:first] + coordinates[i:])
            result2 = split_patch(coordinates[first : i + 1])
            # 			message ("\t*** SPLIT SELF-INTERSECTING/TOUCHING POLYGON: %s\n" % str(coordinates[i]))

            if simple_length(result1[0]) > simple_length(result2[0]):
                result1.extend(result2)
                return result1
            else:
                result2.extend(result1)
                return result2

    return [coordinates]


# Get all app properties from nested XML; recursive search


def get_property(top, ns_app):
    properties = {}
    if ns_app in top.tag:
        tag = top.tag[len(ns_app) + 2 :]
        value = top.text
        value = value.strip()
        if value:
            properties[tag] = value

    for child in top:
        properties.update(get_property(child, ns_app))

    return properties


# Load N50 topo data from Kartverket


def load_n50_data(municipality_id, municipality_name, data_category):
    global gml_id

    lap = time.time()

    message("\nLoad N50 data from Kartverket...\n")

    source_date = ["9", "0"]  # First and last source date ("datafangstdato")
    update_date = ["9", "0"]  # First and last update date ("oppdateringsdato")
    stream_count = 0
    missing_tags = set()

    # Load latest N50 file for municipality from Kartverket

    filename = "Basisdata_%s_%s_25833_N50Kartdata_GML" % (
        municipality_id,
        municipality_name,
    )
    filename = (
        filename.replace("Æ", "E")
        .replace("Ø", "O")
        .replace("Å", "A")
        .replace("æ", "e")
        .replace("ø", "o")
        .replace("å", "a")
        .replace(" ", "_")
    )
    message("\tLoading file '%s'\n" % filename)

    request = urllib.request.Request(
        "https://nedlasting.geonorge.no/geonorge/Basisdata/N50Kartdata/GML/"
        + filename
        + ".zip",
        headers=header,
    )
    file_in = urllib.request.urlopen(request)
    zip_file = zipfile.ZipFile(BytesIO(file_in.read()))

    # 	for file_entry in zip_file.namelist():
    # 		message ("\t%s\n" % file_entry)

    filename2 = filename.replace("Kartdata", data_category)  # For example "Arealdekke"
    file = zip_file.open(filename2 + ".gml")

    tree = ET.parse(file)
    file.close()
    file_in.close()
    root = tree.getroot()

    ns_gml = "http://www.opengis.net/gml/3.2"
    ns_app = "http://skjema.geonorge.no/SOSI/produktspesifikasjon/N50/20170401"

    ns = {"gml": ns_gml, "app": ns_app}

    # Loop features, parse and load into data structure and tag

    message("\tParsing...\n")

    for feature in root:
        if "featureMember" in feature.tag:
            feature_type = feature[0].tag[len(ns_app) + 2 :]
            geometry_type = None
            gml_id = feature[0].attrib["{%s}id" % ns_gml]

            if feature_type not in object_count:
                object_count[feature_type] = 0
            object_count[feature_type] += 1

            if feature_type in avoid_objects and not json_output:
                continue

            entry = {
                "object": feature_type,
                "type": None,
                "gml_id": gml_id,
                "coordinates": [],
                "members": [],
                "tags": {},
                "extras": {"objekttype": feature_type},
            }

            properties = {}  # Attributes provided from GML

            for app in feature[0]:
                # Get app properties/attributes

                tag = app.tag[len(ns_app) + 2 :]
                if tag in ["posisjon", "grense", "område", "senterlinje", "geometri"]:
                    geometry_type = tag
                    entry["extras"]["geometri"] = geometry_type
                else:
                    properties.update(get_property(app, ns_app))

                # Get geometry/coordinates

                for geo in app:
                    # point
                    if geo.tag == "{%s}Point" % ns_gml:
                        entry["type"] = "Point"
                        entry["coordinates"] = parse_coordinates(geo[0].text)[0]

                    # LineString
                    elif geo.tag == "{%s}LineString" % ns_gml:
                        if geometry_type != "geometri":
                            entry["type"] = "LineString"
                            entry["coordinates"] = parse_coordinates(geo[0].text)
                        else:
                            entry["type"] = "Point"
                            entry["coordinates"] = parse_coordinates(geo[0].text)[0]

                    # Curve, stored as LineString
                    elif geo.tag == "{%s}Curve" % ns_gml:
                        entry["type"] = "LineString"
                        entry["extras"]["type2"] = "curve"
                        entry["coordinates"] = []
                        for patch in geo[0]:
                            coordinates = parse_coordinates(patch[0].text)
                            if entry["coordinates"]:
                                entry["coordinates"] + coordinates[1:]
                            else:
                                entry["coordinates"] = coordinates  # First patch

                    # (Multi)Polygon
                    elif geo.tag == "{%s}Surface" % ns_gml:
                        entry["type"] = "Polygon"
                        entry["coordinates"] = []  # List of patches

                        for patch in geo[0][0]:
                            role = patch.tag[len(ns_gml) + 2 :]

                            if patch[0].tag[len(ns_gml) + 2 :] == "Ring":
                                coordinates = parse_coordinates(
                                    patch[0][0][0][0][0][0].text
                                )  # Ring->Curve->LineStringSegment
                            else:
                                coordinates = parse_coordinates(
                                    patch[0][0].text
                                )  # LinearRing

                            if len(coordinates) > 1:
                                if len(coordinates) < 3:
                                    message(
                                        "\t*** POLYGON PATCH TOO SHORT: %s  %s\n"
                                        % (role, gml_id)
                                    )
                                elif coordinates[0] != coordinates[-1]:
                                    message(
                                        "\t*** POLYGON PATCH NOT CLOSED: %s  %s\n"
                                        % (role, gml_id)
                                    )

                                if json_output:
                                    entry["coordinates"].append(coordinates)
                                else:
                                    # Check for intersecting/touching polygon
                                    entry["coordinates"].extend(
                                        split_patch(coordinates)
                                    )
                            else:
                                message(
                                    "\t*** EMPTY POLYGON PATCH: %s  %s\n"
                                    % (role, gml_id)
                                )

                    elif ns_gml in geo.tag:
                        message("\t*** UNKNOWN GEOMETRY: %s\n" % geo.tag)

            # Store tags

            [tags, new_missing_tags] = tag_object(
                feature_type, geometry_type, properties, entry
            )
            entry["tags"].update(tags)
            entry["extras"].update(properties)
            missing_tags.update(new_missing_tags)

            if n50_tags and not debug:
                for key, value in iter(properties.items()):
                    if key not in avoid_tags:
                        entry["tags"]["N50_" + key] = value

            # Add to relevant list

            if not (entry["type"] == "LineString" and len(entry["coordinates"]) <= 1):
                if geometry_type == "grense":
                    if feature_type in [
                        "Kystkontur",
                        "HavElvSperre",
                        "HavInnsjøSperre",
                    ]:
                        entry["used"] = 1
                    else:
                        entry["used"] = 0

                    segments.append(entry)
                elif (
                    not (entry["type"] == "Point" and not entry["tags"]) or debug
                ):  # Omit untagged single points
                    features.append(entry)
            else:
                message("\t*** SEGMENT TOO SHORT: %s\n" % gml_id)

            # Update min/max dates for information

            if "datafangstdato" in properties:
                if (
                    properties["datafangstdato"] < source_date[0]
                    and properties["datafangstdato"] > "1801"
                ):
                    source_date[0] = properties["datafangstdato"]
                if properties["datafangstdato"] > source_date[1]:
                    source_date[1] = properties["datafangstdato"]

            if "oppdateringsdato" in properties:
                if (
                    properties["oppdateringsdato"] < update_date[0]
                    and properties["oppdateringsdato"] > "1801"
                ):
                    update_date[0] = properties["oppdateringsdato"]
                if properties["oppdateringsdato"] > update_date[1]:
                    update_date[1] = properties["oppdateringsdato"]

            if feature_type == "ElvBekk":
                stream_count += 1

    message("\tObjects loaded:\n")
    for object_type in sorted(object_count):
        if object_type not in auxiliary_objects:
            message("\t\t%i\t%s\n" % (object_count[object_type], object_type))

    if missing_tags:
        message("\tNot tagged: %s\n" % ", ".join(missing_tags.difference("Havflate")))
    if stream_count > 0:
        message("\t%i streams\n" % stream_count)

    message("\tSource dates: %s - %s\n" % (source_date[0], source_date[1]))
    message("\tUpdate dates: %s - %s\n" % (update_date[0], update_date[1]))
    message("\t%i feature objects, %i segments\n" % (len(features), len(segments)))
    message("\tRun time %s\n" % (timeformat(time.time() - lap)))


# Create missing KantUtsnitt segments to get complete polygons


def create_border_segments(patch, members, gml_id, match):
    # First create list of existing conncetions between coordinates i and i+1 of patch

    connection = []
    for i in range(len(patch) - 1):
        connection.append(False)

    for member in members:
        segment = segments[member]
        n0 = patch.index(segment["coordinates"][0])

        for node in segment["coordinates"][1:]:
            n1 = patch.index(node)
            if abs(n1 - n0) == 1:
                connection[min(n0, n1)] = True
            elif abs(n1 - n0) == len(patch) - 2:
                connection[len(patch) - 2] = True
            else:
                message(
                    "\t*** MISSING BORDER SEGMENT: Node %i - %i of %i/%i nodes %s\n"
                    % (n0, n1, len(patch), match, gml_id)
                )

            n0 = n1

    # Then create new segments for the parts of patch which have no segments

    start_index = 0
    while start_index < len(patch) - 2:
        while start_index < len(patch) - 1 and connection[start_index]:
            start_index += 1

        end_index = start_index
        while end_index < len(patch) - 1 and not connection[end_index]:
            end_index += 1

        if end_index > start_index:
            entry = {
                "object": "KantUtsnitt",
                "type": "LineString",
                "coordinates": patch[start_index : end_index + 1],
                "members": [],
                "tags": {},
                "extras": {"objekttype": "KantUtsnitt"},
                "used": 1,
            }
            [entry["min_bbox"], entry["max_bbox"]] = get_bbox(entry["coordinates"], 0)
            segments.append(entry)
            members.append(len(segments) - 1)
            start_index = end_index


# Function for sorting member segments of polygon relation
# Index 1 used to avoid equal 0/-1 positions


def segment_position(segment_index, patch):
    return patch.index(segments[segment_index]["coordinates"][1])


# Fix data structure:
# - Split polygons into segments
# - Order direction of ways for coastline, lakes, rivers and islands
# - Order members of multipolygons
# - Crate missing segments along municipality border


def split_polygons():
    message("Decompose polygons into segments...\n")

    # Create bbox for segments and line features

    for segment in segments:
        [segment["min_bbox"], segment["max_bbox"]] = get_bbox(segment["coordinates"], 0)

    # Loop all polygons and patches

    lap = time.time()
    split_count = 0

    for feature in features:
        if feature["type"] == "Polygon":
            matching_polygon = []

            for patch in feature["coordinates"]:
                matching_segments = []
                matched_nodes = 0
                patch_set = set(patch)

                # Try matching with segments within the polygon's bbox

                [patch_min_bbox, patch_max_bbox] = get_bbox(patch, 0)

                for i, segment in enumerate(segments):
                    if (
                        patch_min_bbox[0] <= segment["max_bbox"][0]
                        and patch_max_bbox[0] >= segment["min_bbox"][0]
                        and patch_min_bbox[1] <= segment["max_bbox"][1]
                        and patch_max_bbox[1] >= segment["min_bbox"][1]
                        and set(segment["coordinates"]) <= patch_set
                    ):
                        # Note: If patch is a closed way, segment may wrap start/end of patch

                        if len(segment["coordinates"]) == 2:
                            node1 = patch.index(segment["coordinates"][0])
                            node2 = patch.index(segment["coordinates"][1])
                            if not (
                                abs(node1 - node2) == 1
                                or patch[0] == patch[-1]
                                and abs(node1 - node2) == len(patch) - 2
                            ):
                                continue

                        matching_segments.append(i)
                        matched_nodes += len(segment["coordinates"]) - 1

                        # Correct direction of coastline, lakes and riverways

                        if (
                            feature["object"] == "Havflate"
                            and segment["object"]
                            in ["Kystkontur", "HavElvSperre", "HavInnsjøSperre"]
                            or feature["object"]
                            in [
                                "Innsjø",
                                "InnsjøRegulert",
                                "ElvBekk",
                                "FerskvannTørrfall",
                            ]
                            and segment["object"]
                            in [
                                "Innsjøkant",
                                "InnsjøkantRegulert",
                                "ElvBekkKant",
                                "KantUtsnitt",
                            ]
                        ):
                            segment["used"] += 1
                            node1 = patch.index(segment["coordinates"][0])
                            node2 = patch.index(segment["coordinates"][1])

                            if not (
                                node1 + 1 == node2
                                or patch[0] == patch[-1]
                                and node1 == len(patch) - 2
                                and node2 == 0
                            ):
                                segment["coordinates"].reverse()
                                segment["extras"]["reversert"] = "yes"

                        elif feature["object"] != "Havflate":
                            segment["used"] += 1

                        if matched_nodes == len(patch) - 1:
                            break

                if matching_segments:
                    # Use leftover nodes to create missing border segments
                    if (
                        matched_nodes < len(patch) - 1
                        and feature["object"] != "Havflate"
                    ):
                        create_border_segments(
                            patch, matching_segments, feature["gml_id"], matched_nodes
                        )

                    # Sort relation members for better presentation
                    matching_segments.sort(
                        key=lambda segment_index: segment_position(segment_index, patch)
                    )
                    matching_polygon.append(matching_segments)
                    split_count += len(matching_segments) - 1
                else:
                    message("\t*** NO MATCH: %s\n" % (feature["gml_id"]))
                    feature["extras"]["segmentering"] = "no"

            feature["members"] = matching_polygon

    message("\t%i splits\n" % split_count)
    message("\tRun time %s\n" % (timeformat(time.time() - lap)))


# Fix coastline


def find_islands():
    message("Find islands...\n")

    lap = time.time()
    island_count = 0

    # Part 1: Identify islands described by inner parts of lakes and sea

    # First build list of other candidate relations

    candidates = []
    for feature in features:
        if (
            len(feature["members"]) == 1
            and len(feature["members"][0]) > 1
            and feature["object"]
            not in [
                "Innsjø",
                "InnsjøRegulert",
                "ElvBekk",
                "Havflate",
                "FerskvannTørrfall",
            ]
        ):
            found = True
            for member in feature["members"][0]:
                if segments[member]["object"] not in [
                    "Kystkontur",
                    "Innsjøkant",
                    "InnsjøkantRegulert",
                    "ElvBekkKant",
                ]:
                    found = False
                    break
            if found:
                candidates.append(feature)

    # Loop all inner objects of multipolygon lakes and sea

    for feature in features:
        if feature["object"] in [
            "Innsjø",
            "InnsjøRegulert",
            "ElvBekk",
            "Havflate",
            "FerskvannTørrfall",
        ]:
            for i in range(1, len(feature["members"])):
                # Do not use patch with intermittent edge

                found = True
                for member in feature["members"][i]:
                    if segments[member]["object"] == "FerskvannTørrfallkant":
                        found = False
                        break
                if not found:
                    continue

                # Determine island type based on area

                area = polygon_area(feature["coordinates"][i])

                if abs(area) > island_size:
                    island_type = "island"
                else:
                    island_type = "islet"

                # 				if area < 0:
                # 					message ("\t*** ISLAND WITH REVERSE COASTLINE: %s\n" % feature['gml_id'])

                # Tag closed way if possible

                if len(feature["members"][i]) == 1:
                    segment = segments[feature["members"][i][0]]
                    segment["tags"]["place"] = island_type
                    segment["extras"]["areal"] = str(int(abs(area)))

                else:
                    # Serach for already existing relation

                    found = False
                    for feature2 in candidates:
                        if set(feature["members"][i]) == set(feature2["members"][0]):
                            feature2["tags"]["place"] = island_type
                            feature2["extras"]["areal"] = str(int(abs(area)))
                            break

                    # Else create new polygon

                    if not found:
                        entry = {
                            "object": "Øy",
                            "type": "Polygon",
                            "coordinates": copy.deepcopy(feature["coordinates"][i]),
                            "members": [copy.deepcopy(feature["members"][i])],
                            "tags": {"place": island_type},
                            "extras": {"areal": str(int(abs(area)))},
                        }

                        features.append(entry)

                island_count += 1

    # Part 2: Identify remaining islands
    # Note: This section will also find all lakes, so check coastline direction

    # First build unordered list of segment coastline

    coastlines = []
    # 	for i, segment in enumerate(segments):
    # 		if segment['object'] in ["Kystkontur", "Innsjøkant", "InnsjøkantRegulert", "ElvBekkKant"] and i not in used_segments:
    # 			coastlines.append(segment)

    for feature in features:
        if (
            feature["object"]
            in ["Havflate", "Innsjø", "InnsjøRegulert", "ElvBekk", "FerskvannTørrfall"]
            and len(feature["members"]) > 0
        ):
            for member in feature["members"][0]:  # Only outer patch
                segment = segments[member]
                if segment["object"] in [
                    "HavElvSperre",
                    "HavInnsjøSperre",
                    "InnsjøInnsjøSperre",
                    "InnsjøElvSperre",
                    "FerskvannTørrfallkant",
                    "FiktivDelelinje",
                ]:
                    for member2 in feature["members"][0]:
                        segment2 = segments[member2]
                        if segment2["object"] in [
                            "Kystkontur",
                            "Innsjøkant",
                            "InnsjøkantRegulert",
                            "ElvBekkKant",
                        ]:
                            coastlines.append(segment2)
                    break

    # Merge coastline segments until exhausted

    while coastlines:
        segment = coastlines[0]
        island = [coastlines[0]]
        coastlines.pop(0)
        first_node = segment["coordinates"][0]
        last_node = segment["coordinates"][-1]

        # Build coastline/island forward

        found = True
        while found and first_node != last_node:
            found = False
            for segment in coastlines[:]:
                if segment["coordinates"][0] == last_node:
                    last_node = segment["coordinates"][-1]
                    island.append(segment)
                    coastlines.remove(segment)
                    found = True
                    break

        # Build coastline/island backward
        """
		found = True
		while found and first_node != last_node:
			found = False
			for segment in coastlines[:]:
				if segment['coordinates'][-1] == first_node:
					first_node = segment['coordinates'][0]
					island.insert(0, segment)
					coastlines.remove(segment)
					found = True				
					break
		"""

        # Add island to features list if closed chain of ways

        if first_node == last_node:
            members = []
            coordinates = [first_node]
            for segment in island:
                members.append(segments.index(segment))
                coordinates += segment["coordinates"][1:]

            area = polygon_area(coordinates)
            if area < 0:
                continue

            if abs(area) > island_size:
                island_type = "island"
            else:
                island_type = "islet"

            # Reuse existing relation if possible

            found = False
            for feature in candidates:
                if set(members) == set(feature["members"][0]):
                    feature["tags"]["place"] = island_type
                    feature["extras"]["areal"] = str(int(abs(area)))
                    island_count += 1
                    found = True
                    break

            # Else create new relation for island

            if not found:
                entry = {
                    "object": "Øy",
                    "type": "Polygon",
                    "coordinates": [coordinates],
                    "members": [members],
                    "tags": copy.deepcopy(island[0]["tags"]),
                    "extras": copy.deepcopy(island[0]["extras"]),
                }

                entry["tags"]["place"] = island_type
                entry["tags"].pop(
                    "natural", None
                )  # Remove natural=coastline (already on segments)
                entry["extras"]["areal"] = str(int(abs(area)))

                features.append(entry)
                island_count += 1

    # Remove Havflate objects, which are not used going forward

    for feature in features[:]:
        if feature["object"] == "Havflate":
            features.remove(feature)

    message("\t%i islands\n" % island_count)
    message("\tRun time %s\n" % (timeformat(time.time() - lap)))


# Identify common intersection nodes between lines (e.g. streams)


def match_nodes():
    global delete_count

    message("Identify intersections...\n")

    lap = time.time()
    node_count = len(nodes)
    delete_count = 0

    # Create set of common nodes for segment intersections

    for segment in segments:
        if segment["used"] > 0:
            nodes.add(segment["coordinates"][0])
            nodes.add(segment["coordinates"][-1])

    for feature in features:
        if feature["type"] == "LineString":
            nodes.add(feature["coordinates"][0])
            nodes.add(feature["coordinates"][-1])

    if not no_node:
        # Create bbox for segments and line features + create temporary list of LineString features

        for segment in segments:
            [segment["min_bbox"], segment["max_bbox"]] = get_bbox(
                segment["coordinates"], 0
            )

        # Loop streams to identify intersections with segments

        for feature in features:
            if feature["type"] == "LineString" and feature["object"] == "ElvBekk":
                [feature["min_bbox"], feature["max_bbox"]] = get_bbox(
                    feature["coordinates"], 0
                )

                for segment in segments:
                    if (segment["used"] > 0 or debug) and (
                        feature["min_bbox"][0] <= segment["max_bbox"][0]
                        and feature["max_bbox"][0] >= segment["min_bbox"][0]
                        and feature["min_bbox"][1] <= segment["max_bbox"][1]
                        and feature["max_bbox"][1] >= segment["min_bbox"][1]
                    ):
                        intersections = set(feature["coordinates"]).intersection(
                            set(segment["coordinates"])
                        )
                        if len(intersections) == 0:
                            continue

                        for node in intersections:
                            index1 = feature["coordinates"].index(node)
                            index2 = segment["coordinates"].index(node)

                            # First check if stream node may be removed og slightly relocated

                            if (
                                index1 not in [0, len(feature["coordinates"]) - 1]
                                and node not in nodes
                            ):
                                if (
                                    feature["coordinates"][index1 - 1]
                                    not in intersections
                                    and feature["coordinates"][index1 + 1]
                                    not in intersections
                                ):
                                    feature["coordinates"].pop(index1)
                                else:
                                    lon, lat = node
                                    offset = 10 ** (
                                        -coordinate_decimals + 1
                                    )  # Last lat/lon decimal digit
                                    feature["coordinates"][index1] = (
                                        lon + 4 * offset,
                                        lat + 2 * offset,
                                    )
                                    # Note: New node used in next test here

                                # Then check if segment node may also be removed

                                if index2 not in [0, len(segment["coordinates"]) - 1]:
                                    if (
                                        segment["coordinates"][index2 - 1]
                                        not in intersections
                                        and segment["coordinates"][index2 + 1]
                                        not in intersections
                                    ):
                                        segment["coordinates"].pop(index2)

                            # Else create new common node with "water" segments (or reuse existing common node)

                            elif segment["object"] in [
                                "Kystkontur",
                                "Innsjøkant",
                                "InnsjøkantRegulert",
                                "ElvBekkKant",
                            ]:
                                nodes.add(node)

    # Loop auxiliary lines and simplify geometry

    for segment in segments:
        if segment["used"] > 0 and segment["object"] == "FiktivDelelinje":
            delete_count += len(segment["coordinates"]) - 2
            segment["coordinates"] = [
                segment["coordinates"][0],
                segment["coordinates"][-1],
            ]

    message(
        "\t%i common nodes, %i nodes removed from streams and auxiliary lines\n"
        % (len(nodes) - node_count, delete_count)
    )
    message("\tRun time %s\n" % (timeformat(time.time() - lap)))


# OLD:
# Get elevation for a given node/coordinate
# API reference: https://kartverket.no/api-og-data/friluftsliv/hoydeprofil
# 	and: https://wms.geonorge.no/skwms1/wps.elevation2?request=DescribeProcess&service=WPS&version=1.0.0&identifier=elevation
# Note: Slow api (approx 1.4 calls/second), to be replaced by Kartverket end of 2020


def get_elevation_old(node):
    global elevations, ele_count, retry_count

    ns_ows = "http://www.opengis.net/ows/1.1"
    ns_wps = "http://www.opengis.net/wps/1.0.0"

    ns = {"ns0": ns_wps, "ns2": ns_ows}

    url = (
        "https://wms.geonorge.no/skwms1/wps.elevation2?request=Execute&service=WPS&version=1.0.0&identifier=elevation"
        + "&datainputs=lat=%f;lon=%f;epsg=4326" % (node[1], node[0])
    )

    if node in elevations:
        return elevations[node]

    request = urllib.request.Request(url, headers=header)

    max_retry = 5
    for retry in range(1, max_retry + 1):
        try:
            file = urllib.request.urlopen(request)
            if retry > 1:
                message("\n")
            break

        except urllib.error.HTTPError as e:
            if retry < max_retry:
                message("\tRetry #%i " % retry)
                time.sleep(2 ** (retry - 1))  # First retry after 1 second
                retry_count += 1
            else:
                message("\t*** ELEVATION API UNAVAILABLE\n")
                tree = ET.parse(e)
                root = tree.getroot()
                exception_text = root[0][0].text

                if "exceptionCode" in root[0].attrib:
                    exception_code = root[0].attrib["exceptionCode"]
                else:
                    exception_code = ""

                message("\tHTTP Error %s: %s  " % (e.code, e.reason))
                message("\tException: [%s] %s\n" % (exception_code, exception_text))
                return None

    tree = ET.parse(file)
    file.close()
    root = tree.getroot()

    ele_tag = root.find(
        'ns0:ProcessOutputs/ns0:Output[ns2:Identifier="elevation"]/ns0:Data/ns0:LiteralData',
        ns,
    )
    ele = float(ele_tag.text)

    if math.isnan(ele):
        ele = None
    if ele is None:
        message(" *** NO ELEVATION: %s \n" % str(node))

    elevations[node] = ele  # Store for possible identical request later
    ele_count += 1

    return ele


# NEW:
# Get elevation for a given node/coordinate
# Note: Still testing this api
# Note: Slow api, approx 4 calls / second


def get_elevation(node):
    global elevations, ele_count, retry_count

    url = (
        "https://ws.geonorge.no/hoydedata/v1/punkt?nord=%f&ost=%f&geojson=false&koordsys=4258"
        % (node[1], node[0])
    )
    # 	url = "https://wstest.geonorge.no/hoydedata/v1/punkt?nord=%f&ost=%f&geojson=false&koordsys=4258" % (node[1], node[0])
    # 	url =  "https://wstest.geonorge.no/hoydedata/v1/punkt?nord=60.1&koordsys=4258&geojson=false&ost=11.1"
    # 	message ("%s\n" % url)

    if node in elevations:
        return elevations[node]

    request = urllib.request.Request(url, headers=header)
    file = urllib.request.urlopen(request)

    result = json.load(file)
    file.close()
    # 	message ("Result: %s\n" % str(result))
    # 	ele = result['features'][0]['geometry']['coordinates'][2]
    ele = result["punkter"][0]["z"]
    elevations[node] = ele  # Store for possible identical request later
    ele_count += 1

    if ele is None:
        message(" *** NO ELEVATION: %s \n" % str(result))
    # 		ele = 0.0

    return ele


# Turn streams which have uphill direction


def fix_stream_direction():
    global elevations, ele_count, retry_count

    elevations = {}  # Already fetched elevations from api
    ele_count = 0  # Numbr of api calls during program execution
    retry_count = 0  # Number of retry to api
    max_error = 1.0  # Meters of elevation difference

    lap = time.time()

    message("Load elevation data from Kartverket and reverse streams...\n")

    stream_count = 0
    for feature in features:
        if feature["object"] == "ElvBekk" and feature["type"] == "LineString":
            stream_count += 1

    message("\t%i streams\n" % stream_count)

    api_count = stream_count
    reverse_count = 0

    # Loop all streams and check elevation difference between first and last nodes

    for feature in features:
        if feature["object"] == "ElvBekk" and feature["type"] == "LineString":
            api_count -= 1

            message("\r\t%i " % api_count)

            ele_start = get_elevation(feature["coordinates"][0])
            if ele_start is None:
                continue

            ele_end = get_elevation(feature["coordinates"][-1])
            if ele_end is None:
                continue

            # Reverse direction of stream if within error margin

            if ele_end - ele_start >= max_error:
                feature["coordinates"].reverse()
                reverse_count += 1
                feature["extras"]["reversert"] = "%.2f" % (ele_end - ele_start)
            else:
                feature["extras"]["bekk"] = "%.2f" % (ele_end - ele_start)

            if abs(ele_end - ele_start) < 2 * max_error:
                feature["tags"][
                    "fixme"
                ] = "Please check direction (%.1fm elevation)" % (ele_end - ele_start)

    if retry_count > 0:
        message("\t%i retry to api\n" % retry_count)

    duration = time.time() - lap
    message(
        "\r\t%i streams, %i reversed, %i api calls\n"
        % (stream_count, reverse_count, ele_count)
    )
    message(
        "\tRun time %s, %.2f streams per second\n"
        % (timeformat(duration), stream_count / duration)
    )


# Load place names from SSR within given bbox


def get_ssr_name(feature, name_categories):
    global ssr_places, name_count

    if feature["type"] == "Point":
        bbox = get_bbox(
            feature["coordinates"], 500
        )  # 500 meters perimeter to each side
    else:
        bbox = get_bbox(feature["coordinates"], 0)

    if type(feature["coordinates"][0]) is tuple:
        polygon = feature["coordinates"]
    else:
        polygon = feature["coordinates"][0]

    found_names = []
    names = []

    # Find name in stored file

    for place in ssr_places:
        if (
            bbox[0][0] <= place["coordinate"][0] <= bbox[1][0]
            and bbox[0][1] <= place["coordinate"][1] <= bbox[1][1]
            and place["tags"]["ssr:type"] in name_categories
            and place["tags"]["name"] not in names
            and (
                feature["type"] == "Point"
                or inside_polygon(place["coordinate"], polygon)
            )
        ):
            found_names.append(place)
            names.extend(
                place["tags"]["name"].replace(" - ", ";").split(";")
            )  # Split multiple languages + variants

    # Sort and select name

    if found_names:
        found_names.sort(
            key=lambda name: name_categories.index(name["tags"]["ssr:type"])
        )  # place_name_rank(name, name_categories))

        alt_names = []
        sea = "Sjø" in found_names[0]["tags"]["ssr:type"]
        for place in found_names:
            if not sea or "Sjø" in place["tags"]["ssr:type"]:
                alt_names.append(
                    "%s [%s %s]"
                    % (
                        place["tags"]["name"],
                        place["tags"]["ssr:type"],
                        place["tags"]["ssr:stedsnr"],
                    )
                )

        # Name already suggested by NVE data, so get ssr:stedsnr and any alternative names
        if "name" in feature["tags"] and feature["tags"]["name"] in names:
            name = feature["tags"]["name"]
            for place in found_names:
                if name in place["tags"]["name"].replace(" - ", ";").split(";"):
                    feature["tags"].update(place["tags"])
                    feature["tags"]["name"] = name  # Add back NVE name
                    feature["extras"]["ssr:type"] = feature["tags"].pop(
                        "ssr:type", None
                    )
                    if len(alt_names) > 1:
                        if name != place["tags"]["name"]:
                            alt_names.insert(0, "%s [NVE]" % name)
                        feature["tags"]["fixme"] = "Alternative names: " + ", ".join(
                            alt_names
                        )
                    name_count += 1
                    break

        # Only one name found, or only one name of preferred type
        elif (
            len(alt_names) == 1
            or "øyISjø" in found_names[0]["tags"]["ssr:type"]
            and "øyISjø" not in found_names[1]["tags"]["ssr:type"]
            or "øy" in found_names[0]["tags"]["ssr:type"]
            and "øy" not in found_names[1]["tags"]["ssr:type"]
            or "holme" in found_names[0]["tags"]["ssr:type"]
            and "holme" not in found_names[1]["tags"]["ssr:type"]
        ):
            if "name" in feature["tags"] and (
                len(alt_names) > 1
                or feature["tags"]["name"]
                not in found_names[0]["tags"]["name"].replace(" - ", ";").split(";")
            ):
                alt_names.insert(0, "%s [NVE]" % feature["tags"]["name"])

            feature["tags"].update(found_names[0]["tags"])
            feature["extras"]["ssr:type"] = feature["tags"].pop("ssr:type", None)
            if len(alt_names) > 1:
                feature["tags"]["fixme"] = "Alternative names: " + ", ".join(alt_names)
            name_count += 1

        else:
            feature["tags"]["fixme"] = "Consider names: " + ", ".join(alt_names)

        return found_names[0]["coordinate"]

    else:
        return None


# Get place names for a category


def get_category_place_names(n50_categories, ssr_categories):
    for feature in features:
        if feature["object"] in n50_categories:
            get_ssr_name(feature, ssr_categories)


# Get place names for islands, glaciers etc.
# Place name categories: https://github.com/osmno/geocode2osm/blob/master/navnetyper.json


def get_place_names():
    global ssr_places, name_count
    global elevations, ele_count, retry_count

    message("Load place names from SSR...\n")

    elevations = {}
    ele_count = 0
    retry_count = 0

    lap = time.time()
    name_count = 0
    ssr_places = []

    # Load all SSR place names in municipality

    url = "https://obtitus.github.io/ssr2_to_osm_data/data/%s/%s.osm" % (
        municipality_id,
        municipality_id,
    )
    request = urllib.request.Request(url, headers=header)
    file = urllib.request.urlopen(request)

    tree = ET.parse(file)
    file.close()
    root = tree.getroot()

    for node in root.iter("node"):
        entry = {
            "coordinate": (float(node.get("lon")), float(node.get("lat"))),
            "tags": {},
        }
        for tag in node.iter("tag"):
            if "name" in tag.get("k") or tag.get("k") in ["ssr:stedsnr", "ssr:type"]:
                if tag.get("k") == "fixme":
                    if "multiple name" in tag.get("v"):
                        entry["tags"]["fixme"] = (
                            "Multiple name tags, please choose one and add the other to"
                            " alt_name"
                        )
                else:
                    entry["tags"][tag.get("k")] = tag.get("v")

        ssr_places.append(entry)

    message("\t%s place names in SSR file\n" % len(ssr_places))

    # Get island names

    name_category = [
        "øyISjø",
        "øygruppeISjø",
        "holmeISjø",
        "skjærISjø",
        "øy",
        "øygruppe",
        "holme",
        "skjær",
    ]
    for elements in [segments, features]:
        for element in elements:
            if "place" in element["tags"] and element["tags"]["place"] in [
                "island",
                "islet",
            ]:
                get_ssr_name(element, name_category)

    # Get lake names + missing elevations for lakes

    if lake_ele and data_category == "Arealdekke":
        message("\tLoading lake elevations...\n")

    name_category = [
        "innsjø",
        "delAvInnsjø",
        "vann",
        "gruppeAvVann",
        "kanal",
        "gruppeAvTjern",
        "tjern",
        "lon",
        "pytt",
    ]
    lake_ele_count = 0

    for feature in features:
        if feature["object"] in ["Innsjø", "InnsjøRegulert"]:
            lake_node = get_ssr_name(feature, name_category)
            area = abs(multipolygon_area(feature["coordinates"]))
            feature["extras"]["areal"] = str(int(area))

            # Get lake's elevation if missing, and if lake is larger than threshold

            if (
                lake_ele
                and "ele" not in feature["tags"]
                and (lake_node or area >= lake_ele_size)
            ):
                # Check that name coordinate is not on lake's island
                if lake_node:
                    if not inside_multipolygon(lake_node, feature["coordinates"]):
                        lake_node = None
                    else:
                        feature["extras"]["elevation"] = "Based on lake name position"

                # If name coordinate cannot be used, try centroid
                if lake_node is None:
                    lake_node = polygon_centroid(feature["coordinates"][0])
                    feature["extras"]["elevation"] = "Based on centroid"
                    if not inside_multipolygon(lake_node, feature["coordinates"]):
                        lake_node = None

                # If all fail, just use coordinate of first node on lake perimeter
                if lake_node is None:
                    lake_node = feature["coordinates"][0][0]
                    feature["extras"]["elevation"] = "Based on first node"

                if lake_node:
                    ele = get_elevation(lake_node)
                    if ele:
                        feature["tags"]["ele"] = str(int(round(ele)))
                        create_point(lake_node, "", "elevation %.1f" % ele)
                        lake_ele_count += 1
                        message("\r\t%i " % lake_ele_count)

    # Create lake centroid nodes for debugging
    for feature in features:
        if feature["object"] in ["Innsjø", "InnsjøRegulert"]:
            centroid = polygon_centroid(feature["coordinates"][0])
            create_point(centroid, feature["gml_id"], "centroid")

    # Get glacier names
    get_category_place_names(["SnøIsbre"], ["isbre", "fonn", "iskuppel"])

    # Get wetland names
    get_category_place_names(["Myr"], ["myr", "våtmarksområde"])

    # Get cemetery names
    get_category_place_names(["Gravplass"], ["gravplass"])

    # Get piste names
    get_category_place_names(["Alpinbakke"], ["alpinanlegg", "skiheis"])

    # Get dam names
    get_category_place_names(["Steintipp"], ["dam"])

    # Get waterfall (point)
    get_category_place_names(["Foss"], ["foss", "stryk"])

    message("\r\t%i place names found\n" % name_count)
    if lake_ele:
        message("\t%i lake elevations found\n" % lake_ele_count)
    message("\tRun time %s\n" % (timeformat(time.time() - lap)))


# Get name from NVE Innsjødatabasen
# API reference: https://gis3.nve.no/map/rest/services/Innsjodatabase2/MapServer


def get_nve_lakes():
    message("Load lake data from NVE...\n")

    n50_lake_count = 0
    nve_lake_count = 0
    more_lakes = True
    lakes = {}

    # Paging results (default 1000 lakes)

    while more_lakes:
        # 		Alternative url:
        # 		url = "https://gis3.nve.no/map/rest/services/Innsjodatabase2/MapServer/find?" + \
        # 				"searchText=%s&contains=true&searchFields=kommNr&layers=5&returnGeometry=false&returnUnformattedValues=true&f=pjson&resultOffset=%i&resultRecordCount=1000&orderByFields=areal_km2%20DESC" \
        # 				% (municipality_id, nve_lake_count)

        # 		url = "https://gis3.nve.no/map/rest/services/Innsjodatabase2/MapServer/5/query?" + \
        # 				"where=kommNr%%3D%%27%s%%27&outFields=vatnLnr%%2Cnavn%%2Choyde%%2Careal_km2%%2CmagasinNr&returnGeometry=false&resultOffset=%i&resultRecordCount=1000&f=json" \
        # 					% (municipality_id, nve_lake_count)

        url = (
            "https://nve.geodataonline.no/arcgis/rest/services/Innsjodatabase2/MapServer/5/query?"
            + "where=kommNr%%3D%%27%s%%27&outFields=vatnLnr%%2Cnavn%%2Choyde%%2Careal_km2%%2CmagasinNr&returnGeometry=false&resultOffset=%i&resultRecordCount=1000&f=json"
            % (municipality_id, nve_lake_count)
        )

        request = urllib.request.Request(url, headers=header)
        file = urllib.request.urlopen(request)
        lake_data = json.load(file)
        file.close()

        for lake_result in lake_data["features"]:
            lake = lake_result["attributes"]
            entry = {
                "name": lake["navn"],
                "ele": lake["hoyde"],
                "area": lake["areal_km2"],
                "mag_id": lake["magasinNr"],
            }
            lakes[str(lake["vatnLnr"])] = entry

        nve_lake_count += len(lake_data["features"])

        if "exceededTransferLimit" not in lake_data:
            more_lakes = False

    # Update lake info

    for feature in features:
        if "ref:nve:vann" in feature["tags"]:
            ref = feature["tags"]["ref:nve:vann"]
            if ref in lakes:
                if lakes[ref]["name"]:
                    feature["tags"]["name"] = lakes[ref]["name"]
                if lakes[ref]["ele"] and "ele" not in feature["tags"]:
                    feature["tags"]["ele"] = str(lakes[ref]["ele"])
                if lakes[ref]["area"] > 1 and "water" not in feature["tags"]:
                    feature["tags"]["water"] = "lake"
                if lakes[ref]["mag_id"]:
                    feature["tags"]["ref:nve:magasin"] = str(lakes[ref]["mag_id"])
                feature["extras"]["nve_areal"] = str(
                    int(lakes[ref]["area"] * 1000000)
                )  # Square meters

        if feature["object"] in ["Innsjø", "InnsjøRegulert"]:
            n50_lake_count += 1

    message(
        "\t%i N50 lakes matched against %i NVE lakes\n"
        % (n50_lake_count, nve_lake_count)
    )


# Save geojson file for reviewing raw input data from GML file


def save_geojson(filename):
    message("Save to '%s' file...\n" % filename)

    json_features = {"type": "FeatureCollection", "features": []}

    for feature_list in [features, segments]:
        for feature in feature_list:
            entry = {
                "type": "Feature",
                "geometry": {
                    "type": feature["type"],
                    "coordinates": feature["coordinates"],
                },
                "properties": dict(
                    feature["extras"].items()
                    + feature["tags"].items()
                    + {"gml_id": gml_id}.items()
                ),
            }

            json_features["features"].append(entry)

    file = open(filename, "w")
    json.dump(json_features, file, indent=2)
    file.close()

    message("\t%i features saved\n" % len(features))


# Indent XML output


def indent_tree(elem, level=0):
    i = "\n" + level * "  "
    if len(elem):
        if not elem.text or not elem.text.strip():
            elem.text = i + "  "
        if not elem.tail or not elem.tail.strip():
            elem.tail = i
        for elem in elem:
            indent_tree(elem, level + 1)
        if not elem.tail or not elem.tail.strip():
            elem.tail = i
    else:
        if level and (not elem.tail or not elem.tail.strip()):
            elem.tail = i


# Save osm file


def save_osm(filename):
    message("Save to '%s' file...\n" % filename)

    osm_node_ids = {}  # Will contain osm_id of each common node
    relation_count = 0
    way_count = 0
    node_count = 0

    osm_root = ET.Element(
        "osm", version="0.6", generator="n50osm v" + version, upload="false"
    )
    osm_id = -1000

    # Common nodes

    for node in nodes:
        osm_id -= 1
        osm_node = ET.Element(
            "node", id=str(osm_id), action="modify", lat=str(node[1]), lon=str(node[0])
        )
        osm_root.append(osm_node)
        osm_node_ids[node] = osm_id
        node_count += 1

    # Ways used by relations

    for segment in segments:
        if segment["used"] > 0 or debug:  # or segment['object'] == "Kystkontur":
            osm_id -= 1
            osm_feature = ET.Element("way", id=str(osm_id), action="modify")
            osm_root.append(osm_feature)
            segment["osm_id"] = osm_id
            segment["etree"] = osm_feature
            way_count += 1

            for node in segment["coordinates"]:
                if node in nodes:
                    osm_nd = ET.Element("nd", ref=str(osm_node_ids[node]))
                else:
                    osm_id -= 1
                    osm_node = ET.Element(
                        "node",
                        id=str(osm_id),
                        action="modify",
                        lat=str(node[1]),
                        lon=str(node[0]),
                    )
                    osm_root.append(osm_node)
                    osm_nd = ET.Element("nd", ref=str(osm_id))
                    node_count += 1
                osm_feature.append(osm_nd)

            for key, value in iter(segment["tags"].items()):
                osm_tag = ET.Element("tag", k=key, v=value)
                osm_feature.append(osm_tag)

            if debug:
                for key, value in iter(segment["extras"].items()):
                    osm_tag = ET.Element("tag", k=key.upper(), v=value)
                    osm_feature.append(osm_tag)

    # The main objects

    for feature in features:
        if feature["object"] == "Havflate":
            continue

        if feature["type"] == "Point":
            osm_id -= 1
            osm_feature = ET.Element(
                "node",
                id=str(osm_id),
                action="modify",
                lat=str(feature["coordinates"][1]),
                lon=str(feature["coordinates"][0]),
            )
            osm_root.append(osm_feature)
            node_count += 1

        elif feature["type"] in "LineString":
            osm_id -= 1
            osm_feature = ET.Element("way", id=str(osm_id), action="modify")
            osm_root.append(osm_feature)
            way_count += 1

            for node in feature["coordinates"]:
                if node in nodes:
                    osm_nd = ET.Element("nd", ref=str(osm_node_ids[node]))
                else:
                    osm_id -= 1
                    osm_node = ET.Element(
                        "node",
                        id=str(osm_id),
                        action="modify",
                        lat=str(node[1]),
                        lon=str(node[0]),
                    )
                    osm_root.append(osm_node)
                    osm_nd = ET.Element("nd", ref=str(osm_id))
                    node_count += 1
                osm_feature.append(osm_nd)

        elif feature["type"] == "Polygon":
            # Output way if possible to avoid relation
            if (
                len(feature["members"]) == 1
                and len(feature["members"][0]) == 1
                and not (
                    "natural" in feature["tags"]
                    and "natural" in segments[feature["members"][0][0]]["tags"]
                )
            ):
                osm_feature = segments[feature["members"][0][0]]["etree"]

            else:
                osm_id -= 1
                osm_feature = ET.Element("relation", id=str(osm_id), action="modify")
                osm_root.append(osm_feature)
                relation_count += 1
                role = "outer"

                for patch in feature["members"]:
                    for member in patch:
                        osm_member = ET.Element(
                            "member",
                            type="way",
                            ref=str(segments[member]["osm_id"]),
                            role=role,
                        )
                        osm_feature.append(osm_member)
                    role = "inner"

                osm_tag = ET.Element("tag", k="type", v="multipolygon")
                osm_feature.append(osm_tag)

        else:
            message("\t*** UNKNOWN GEOMETRY: %s\n" % feature["type"])

        for key, value in iter(feature["tags"].items()):
            osm_tag = ET.Element("tag", k=key, v=value)
            osm_feature.append(osm_tag)

        if debug:
            for key, value in iter(feature["extras"].items()):
                osm_tag = ET.Element("tag", k=key.upper(), v=value)
                osm_feature.append(osm_tag)

    osm_root.set("upload", "false")
    indent_tree(osm_root)
    osm_tree = ET.ElementTree(osm_root)
    osm_tree.write(filename, encoding="utf-8", method="xml", xml_declaration=True)

    message(
        "\t%i relations, %i ways, %i nodes saved\n"
        % (relation_count, way_count, node_count)
    )


# Main program

if __name__ == "__main__":
    start_time = time.time()
    message("\n-- n50osm v%s --\n" % version)

    features = []  # All geometry and tags
    segments = []  # Line segments which are shared by one or more polygons
    nodes = (
        set()
    )  # Common nodes at intersections, including start/end nodes of segments [lon,lat]
    building_tags = {}  # Conversion table from building type to osm tag
    object_count = {}  # Count loaded object types

    debug = False  # Include debug tags and unused segments
    n50_tags = False  # Include property tags from N50 in output
    json_output = False  # Output complete and unprocessed geometry in geojson format
    turn_stream = False  # Load elevation data to check direction of streams
    lake_ele = False  # Load elevation for lakes
    no_name = False  # Do not load SSR place names
    no_nve = False  # Do not load NVE lake data
    no_node = False  # Do not merge common nodes at intersections

    # Parse parameters

    if len(sys.argv) < 3:
        message("Please provide 1) municipality, and 2) data category parameter.\n")
        message("Data categories: %s\n" % ", ".join(data_categories))
        message(
            "Options: -debug, -tag, -geojson, -stream, -ele, -noname, -nonve,"
            " -nonode\n\n"
        )
        sys.exit()

    # Get municipality

    municipality_query = sys.argv[1]
    [municipality_id, municipality_name] = get_municipality_name(municipality_query)
    if municipality_id is None:
        sys.exit("Municipality '%s' not found\n" % municipality_query)
    else:
        message("Municipality:\t%s %s\n" % (municipality_id, municipality_name))

    # Get N50 data category

    data_category = None
    for category in data_categories:
        if sys.argv[2].lower() in category.lower():
            data_category = category
            message("N50 category:\t%s\n" % data_category)
            break
    if not data_category:
        sys.exit("Please provide data category: %s\n" % ", ".join(data_categories))

    # Get other options

    if "-debug" in sys.argv:
        debug = True
    if "-tag" in sys.argv or "-tags" in sys.argv:
        n50_tags = True
    if "-geojson" in sys.argv or "-json" in sys.argv:
        json_output = True
    if "-stream" in sys.argv or "-bekk" in sys.argv:
        turn_stream = True
    if "-ele" in sys.argv or "-høyde" in sys.argv:
        lake_ele = True
    if "-noname" in sys.argv:
        no_name = True
    if "-nonve" in sys.argv:
        no_nve = True
    if "-nonode" in sys.argv:
        no_node = True

    if not turn_stream or not lake_ele:
        message("*** Remember -stream and -ele options before importing.\n")

    output_filename = "n50_%s_%s_%s" % (
        municipality_id,
        municipality_name.replace(" ", "_"),
        data_category,
    )

    # Process data

    if data_category == "BygningerOgAnlegg":
        load_building_types()

    load_n50_data(municipality_id, municipality_name, data_category)

    if json_output:
        save_geojson(output_filename + ".geojson")
    else:
        split_polygons()
        if data_category == "Arealdekke":
            if turn_stream:
                fix_stream_direction()  # Note: Slow api
            if not no_nve:
                get_nve_lakes()
            find_islands()  # Note: "Havflate" is removed at the end of this process
            if not no_name:
                get_place_names()
        match_nodes()
        save_osm(output_filename + ".osm")

    duration = time.time() - start_time
    message(
        "\tTotal run time %s (%i features per second)\n\n"
        % (timeformat(duration), int(len(features) / duration))
    )
