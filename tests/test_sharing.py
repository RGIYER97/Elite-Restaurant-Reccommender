import pytest

from restaurant_finder.sharing import SharedCollection, decode_collection, encode_collection


def test_collection_share_token_round_trips() -> None:
    original = SharedCollection(
        name="Date night",
        location="Flatiron, NYC",
        place_types=("restaurant", "bar"),
        place_ids=("one", "two"),
    )

    assert decode_collection(encode_collection(original)) == original


def test_collection_share_token_rejects_invalid_payload() -> None:
    with pytest.raises(ValueError):
        decode_collection("not-valid-base64!!!")
