import pytest

from restaurant_finder.sharing import SharedCollection, decode_collection, encode_collection


def test_collection_share_token_round_trips() -> None:
    original = SharedCollection(
        name="Date night",
        location="Flatiron, NYC",
        place_types=("restaurant", "bar"),
        place_ids=("one", "two"),
        minimum_review_count=350,
        radius_miles=4.5,
    )

    assert decode_collection(encode_collection(original)) == original


def test_collection_share_token_rejects_invalid_payload() -> None:
    with pytest.raises(ValueError):
        decode_collection("not-valid-base64!!!")


def test_legacy_collection_token_uses_search_defaults() -> None:
    # Version-one links created before search criteria were added omit m and r.
    legacy_token = "eyJ2IjoxLCJuIjoiVHJpcCIsImwiOiJCb3N0b24iLCJ0IjpbImJhciJdLCJwIjpbIm9uZSJdfQ"

    decoded = decode_collection(legacy_token)

    assert decoded.minimum_review_count == 200
    assert decoded.radius_miles == 3.0
