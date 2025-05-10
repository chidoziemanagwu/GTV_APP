from django import template

register = template.Library()

@register.filter
def multiply(value, arg):
    return float(value) * float(arg)

@register.filter
def divide(value, arg):
    try:
        return float(value) / float(arg)
    except (ValueError, ZeroDivisionError):
        return 0