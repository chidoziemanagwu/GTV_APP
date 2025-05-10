# utils/ratelimit.py
from django.core.cache import cache
from django.http import HttpResponse
from functools import wraps
import time

def ratelimit(key_prefix, limit=10, period=60):
    """
    Rate limiting decorator

    Args:
        key_prefix: Prefix for the cache key
        limit: Maximum number of requests
        period: Time period in seconds
    """
    def decorator(view_func):
        @wraps(view_func)
        def _wrapped_view(request, *args, **kwargs):
            # Get client IP
            ip = get_client_ip(request)

            # Create cache key
            key = f"{key_prefix}:{ip}"

            # Get current count and timestamp
            cache_data = cache.get(key)

            if cache_data is None:
                # First request
                cache_data = {
                    'count': 1,
                    'timestamp': time.time()
                }
                cache.set(key, cache_data, period)
                return view_func(request, *args, **kwargs)

            # Check if period has elapsed
            elapsed = time.time() - cache_data['timestamp']

            if elapsed > period:
                # Period elapsed, reset counter
                cache_data = {
                    'count': 1,
                    'timestamp': time.time()
                }
                cache.set(key, cache_data, period)
                return view_func(request, *args, **kwargs)

            # Increment counter
            cache_data['count'] += 1

            # Check if limit exceeded
            if cache_data['count'] > limit:
                return HttpResponse(
                    "Rate limit exceeded. Please try again later.",
                    status=429
                )

            # Update cache
            cache.set(key, cache_data, period)

            return view_func(request, *args, **kwargs)

        return _wrapped_view

    return decorator

def get_client_ip(request):
    """Get client IP address from request"""
    x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
    if x_forwarded_for:
        ip = x_forwarded_for.split(',')[0]
    else:
        ip = request.META.get('REMOTE_ADDR')
    return ip