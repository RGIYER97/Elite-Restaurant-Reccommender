from restaurant_finder.rate_limiter import RateLimiter, RateLimitRule


def test_rate_limiter_blocks_until_the_window_expires() -> None:
    limiter = RateLimiter()
    rules = (RateLimitRule("search", 2, 60),)

    assert limiter.consume("client", rules, now=100).allowed
    assert limiter.consume("client", rules, now=101).allowed
    blocked = limiter.consume("client", rules, now=102)

    assert blocked.allowed is False
    assert blocked.retry_after_seconds == 58
    assert limiter.consume("client", rules, now=161).allowed


def test_rate_limiter_keeps_clients_separate() -> None:
    limiter = RateLimiter()
    rules = (RateLimitRule("search", 1, 60),)

    assert limiter.consume("first", rules, now=100).allowed
    assert limiter.consume("second", rules, now=100).allowed
