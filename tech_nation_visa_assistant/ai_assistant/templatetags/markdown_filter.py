from django import template
import markdown
import bleach

register = template.Library()

@register.filter
def markdown_safe(text):
    """Convert markdown to HTML and sanitize it"""
    allowed_tags = [
        'h1', 'h2', 'h3', 'h4', 'h5', 'h6',
        'p', 'br', 'hr',
        'ul', 'ol', 'li',
        'strong', 'em', 'b', 'i',
        'a', 'code', 'pre',
        'blockquote', 'table', 'thead', 'tbody', 'tr', 'th', 'td'
    ]

    allowed_attrs = {
        'a': ['href', 'title'],
        'th': ['scope'],
        'code': ['class'],
        'pre': ['class']
    }

    html = markdown.markdown(
        text,
        extensions=['extra', 'smarty', 'tables']
    )

    clean_html = bleach.clean(
        html,
        tags=allowed_tags,
        attributes=allowed_attrs,
        strip=True
    )

    return clean_html