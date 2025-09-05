from django import template

register = template.Library()

@register.filter
def add_class(field, css_class):
    """Add CSS class to form field."""
    if hasattr(field, 'as_widget'):
        return field.as_widget(attrs={'class': css_class})
    else:
        # If it's not a form field, return as is
        return field
