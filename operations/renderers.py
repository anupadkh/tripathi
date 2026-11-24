from decimal import Decimal
from rest_framework.renderers import JSONRenderer, BaseRenderer
from rest_framework.utils.encoders import JSONEncoder


class DecimalEncoder(JSONEncoder):
    def default(self, obj):
        if isinstance(obj, Decimal):
            return str(obj)
        return super().default(obj)


class DecimalJSONRenderer(JSONRenderer):
    encoder_class = DecimalEncoder


class InvoicePDFRenderer(BaseRenderer):
    media_type = "application/pdf"
    format = "pdf"
    charset = None

    def render(self, data, accepted_media_type=None, renderer_context=None):
        # The export action returns an HttpResponse directly for successful PDFs.
        # DRF still negotiates the Accept header before calling that action.
        if isinstance(data, bytes):
            return data
        return DecimalJSONRenderer().render(data, renderer_context=renderer_context)
