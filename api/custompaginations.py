from rest_framework.pagination import PageNumberPagination


class RegularPageNumberPagination(PageNumberPagination):
    page_size = 10
    page_size_query_param = 'pagesize'
    max_page_size = 1000


# 不分页的ViewSet, 使用这个类代替缺省的分页类。
class LargeResultsSetPagination(PageNumberPagination):
    page_size = 1000
    page_size_query_param = 'pagesize'
    max_page_size = 10000
