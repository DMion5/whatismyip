"""Tests for saved Aruba site coordinates."""

from whatismyip.aruba_sites import get_aruba_site_location


def test_numbered_residence_sites_have_distinct_coordinates():
    building_801 = get_aruba_site_location("Creekside Village 801")
    building_803 = get_aruba_site_location("Creekside Village 803")

    assert building_801 is not None
    assert building_803 is not None
    assert (building_801["latitude"], building_801["longitude"]) != (
        building_803["latitude"],
        building_803["longitude"],
    )


def test_site_lookup_is_case_and_whitespace_insensitive():
    location = get_aruba_site_location("  capen   HALL ")

    assert location is not None
    assert location["name"] == "Capen Hall"
    assert location["source"] == "ub_interactive_map"


def test_non_fixed_aruba_sites_are_not_mapped():
    assert get_aruba_site_location("UB Buses") is None
    assert get_aruba_site_location("Unmapped") is None
    assert get_aruba_site_location("visualrf_default") is None
