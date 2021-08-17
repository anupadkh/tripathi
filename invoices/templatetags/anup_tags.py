from django import template

register = template.Library()

@register.filter(name="remove_dash")
def remove_dash(value):
    """Removes all values of arg from the given string"""
    if value==None:
        return value
    return value.replace('-', '.')

@register.filter(name="payment_mode")
def payment_mode(value):
    y =dict([(1, "Cheque"), (2, "Cash"), (3,"Bank Transfer"), (4, "Internet Payment"), (5, "Transport"), (6, "Bank Deposit"), (7, "Goods Returned"), (8, "Discount")])
    return y[value]