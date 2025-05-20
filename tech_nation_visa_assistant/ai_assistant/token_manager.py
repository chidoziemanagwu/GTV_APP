# ai_assistant/token_manager.py

import tiktoken
from django.core.cache import cache
import logging
import time
import os
from functools import wraps
from django.http import JsonResponse

logger = logging.getLogger(__name__)

class TokenManager:
    """Manages token usage for AI models to optimize costs and performance"""

    # Token limits by model
    MODEL_LIMITS = {
        "gpt-4": 8192,
        "gpt-4-turbo": 128000,
        "gpt-4.1-nano": 4096,
        "gpt-3.5-turbo": 4096,
        "gemini-pro": 32768
    }

    # Cost per 1K tokens (input/output) in USD
    MODEL_COSTS = {
        "gpt-4": (0.03, 0.06),
        "gpt-4-turbo": (0.01, 0.03),
        "gpt-4.1-nano": (0.0015, 0.003),
        "gpt-3.5-turbo": (0.0015, 0.002),
        "gemini-pro": (0.0005, 0.0015)
    }

    def __init__(self, default_model="gpt-4.1-nano"):
        self.default_model = default_model
        self._encoders = {}

    def get_encoder(self, model):
        """Get or create a tokenizer for the specified model"""
        if model not in self._encoders:
            try:
                self._encoders[model] = tiktoken.encoding_for_model(model)
            except KeyError:
                # Fallback to cl100k_base for models not in tiktoken
                self._encoders[model] = tiktoken.get_encoding("cl100k_base")
        return self._encoders[model]

    def count_tokens(self, text, model=None):
        """Count tokens in a text string"""
        model = model or self.default_model
        encoder = self.get_encoder(model)
        return len(encoder.encode(text))

    def truncate_to_limit(self, text, max_tokens=None, model=None):
        """Truncate text to stay within token limit"""
        model = model or self.default_model
        max_tokens = max_tokens or self.MODEL_LIMITS.get(model, 4000)

        encoder = self.get_encoder(model)
        tokens = encoder.encode(text)

        if len(tokens) <= max_tokens:
            return text

        truncated_tokens = tokens[:max_tokens]
        return encoder.decode(truncated_tokens)

    def estimate_cost(self, input_text, output_text=None, model=None):
        """Estimate cost of API call in USD"""
        model = model or self.default_model
        input_tokens = self.count_tokens(input_text, model)
        output_tokens = 0
        if output_text:
            output_tokens = self.count_tokens(output_text, model)

        input_cost, output_cost = self.MODEL_COSTS.get(model, (0.01, 0.01))
        total_cost = (input_tokens * input_cost / 1000) + (output_tokens * output_cost / 1000)

        return {
            'input_tokens': input_tokens,
            'output_tokens': output_tokens,
            'total_tokens': input_tokens + output_tokens,
            'cost_usd': total_cost
        }

    def get_cached_response(self, prompt, model=None):
        """Get cached response if available"""
        model = model or self.default_model
        cache_key = f"ai_response:{model}:{hash(prompt)}"
        return cache.get(cache_key)

    def cache_response(self, prompt, response, model=None, ttl=86400):
        """Cache AI responses to reduce API calls"""
        model = model or self.default_model
        cache_key = f"ai_response:{model}:{hash(prompt)}"
        cache.set(cache_key, response, ttl)
        return response

    def format_messages(self, system_prompt, user_prompt, conversation_history=None):
        """Format messages for OpenAI API with token optimization"""
        messages = [{"role": "system", "content": system_prompt}]

        # Add conversation history if provided
        if conversation_history:
            # Limit history if needed
            token_count = self.count_tokens(system_prompt)
            history_messages = []

            for msg in conversation_history:
                msg_tokens = self.count_tokens(msg['content'])
                if token_count + msg_tokens > self.MODEL_LIMITS.get(self.default_model, 4000) * 0.75:
                    break
                history_messages.append(msg)
                token_count += msg_tokens

            messages.extend(history_messages)

        # Add user prompt
        messages.append({"role": "user", "content": user_prompt})

        return messages

    def rate_limit(self, key, max_calls=60, window=60):
        """Check if rate limit is exceeded"""
        cache_key = f"rate_limit:{key}"
        calls = cache.get(cache_key, [])

        # Remove timestamps outside the window
        now = time.time()
        calls = [call for call in calls if now - call < window]

        # Check if limit exceeded
        if len(calls) >= max_calls:
            return True

        # Add current call and update cache
        calls.append(now)
        cache.set(cache_key, calls, window)
        return False

# Create a decorator for rate limiting
def rate_limit(max_calls=60, window=60):
    def decorator(view_func):
        @wraps(view_func)
        def _wrapped_view(request, *args, **kwargs):
            token_manager = TokenManager()
            key = f"{view_func.__name__}:{request.user.id}"

            if token_manager.rate_limit(key, max_calls, window):
                return JsonResponse({
                    'error': f'Rate limit exceeded. Maximum {max_calls} calls per {window} seconds.'
                }, status=429)

            return view_func(request, *args, **kwargs)
        return _wrapped_view
    return decorator

# Create a global instance
token_manager = TokenManager()