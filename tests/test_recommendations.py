from restaurant_finder.recommendations import extract_recommended_dishes


def test_extracts_review_summary_dishes_without_generic_claims() -> None:
    dishes = extract_recommended_dishes(
        (
            "Diners like the fresh halal food, especially the flavorful jerk chicken "
            "and lamb gyros, and generous portion sizes."
        ),
        "Casual shop specializing in chicken and lamb platters, plus takeout.",
        (),
    )

    assert "jerk chicken" in dishes
    assert "lamb gyros" in dishes
    assert "generous portion sizes" not in dishes
    assert "chicken" not in dishes


def test_extracts_three_items_from_a_review_summary_list() -> None:
    dishes = extract_recommended_dishes(
        (
            "Diners like the Italian food, especially the pizza, pasta, and "
            "mozzarella sticks, with generous portions."
        ),
        "",
        (),
    )

    assert dishes == ("mozzarella sticks", "pasta", "pizza")


def test_uses_review_order_language_as_a_fallback() -> None:
    dishes = extract_recommended_dishes(
        "",
        "",
        ("We ordered the fish and chips. I recommend the burger.",),
    )

    assert "fish and chips" in dishes
    assert "burger" in dishes


def test_returns_nothing_when_no_dish_is_evidenced() -> None:
    dishes = extract_recommended_dishes(
        "Guests praise the friendly staff and cozy atmosphere.",
        "A welcoming neighborhood restaurant.",
        ("Everything was great.",),
    )

    assert dishes == ()


def test_review_summary_prevents_lower_confidence_review_noise() -> None:
    dishes = extract_recommended_dishes(
        "Guests highlight dishes like brioche sandwiches and ricotta pancakes.",
        "",
        ("We had and enjoyed some coffee after waiting for a table.",),
    )

    assert dishes == ("brioche sandwiches", "ricotta pancakes")
