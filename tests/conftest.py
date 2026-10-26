import os

# Tests must not trip the public-demo rate limiter. Individual rate-limit tests
# construct their own RateLimiter explicitly.
os.environ["SKINMAKER_RATE_LIMIT_PER_MIN"] = "0"
