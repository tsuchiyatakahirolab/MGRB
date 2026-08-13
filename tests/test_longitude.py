from shapely.geometry import LineString

from mgrb.longitude import bbox_360_to_180_parts, lon_to_180, lon_to_360, transform_longitudes


def test_longitude_conventions():
    assert lon_to_360(-170) == 190
    assert lon_to_360(180) == 180
    assert lon_to_180(190) == -170
    # MGRB preserves +180 when the input is the positive antimeridian endpoint.
    assert lon_to_180(180) == 180
    assert lon_to_180(540) == 180
    assert lon_to_180(-180) == -180


def test_pacific_bbox_splits_at_antimeridian():
    assert bbox_360_to_180_parts((100, -60, 300, 70)) == [
        (100, -60, 180.0, 70),
        (-180.0, -60, -60, 70),
    ]


def test_crossing_line_is_continuous_in_360_derivative():
    crossing = LineString([(179.0, 10.0), (-179.0, 11.0)])
    shifted = transform_longitudes(crossing, "360")
    longitudes = [coordinate[0] for coordinate in shifted.coords]
    assert longitudes == [179.0, 181.0]
    assert max(longitudes) - min(longitudes) == 2.0
