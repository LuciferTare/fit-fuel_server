from rest_framework.pagination import PageNumberPagination


class CustomPagination(PageNumberPagination):
    page_size = 20
    page_size_query_param = "page_size"
    max_page_size = 100
    page_query_param = "page"


class OptionalPagination(PageNumberPagination):
    """Paginates only when the caller explicitly passes a positive `page_size`.
    Omitting it (or passing `page_size=0`) returns every matching record in
    one response — the behavior these endpoints have always had."""

    page_size_query_param = "page_size"
    max_page_size = 100
    page_query_param = "page"

    def get_page_size(self, request):
        raw = request.query_params.get(self.page_size_query_param)
        if raw is None:
            return 0
        try:
            page_size = int(raw)
        except (TypeError, ValueError):
            return 0
        return min(page_size, self.max_page_size) if page_size > 0 else 0
