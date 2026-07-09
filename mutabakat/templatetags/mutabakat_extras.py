from decimal import Decimal, InvalidOperation

from django import template

register = template.Library()


@register.filter
def tr_para(value):
    """Sayıyı Türkçe para formatında gösterir: 8535863.55 -> 8.535.863,55"""
    try:
        d = Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError):
        return value
    negatif = d < 0
    d = abs(d)
    tam, kesir = f"{d:.2f}".split(".")
    # Binlik ayraç
    tam_gruplu = f"{int(tam):,}".replace(",", ".")
    sonuc = f"{tam_gruplu},{kesir}"
    return f"-{sonuc}" if negatif else sonuc
