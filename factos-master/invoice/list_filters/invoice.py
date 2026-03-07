from django.contrib import admin


class FromDateFilter(admin.SimpleListFilter):
    title = 'Fecha factura: Desde'
    parameter_name = 'next_download__from_date'
    template = 'factos/admin.html'

    def lookups(self, request, model_admin):
        return ((None, None),)


    def queryset(self, request, queryset):
        value = request.GET.get('next_download__from_date')
        if value:
            return queryset.filter(next_download__from_date=value)
        
        return queryset


class ToDateFilter(admin.SimpleListFilter):
    title = 'Fecha factura: Hasta'
    parameter_name = 'next_download__to_date'
    template = 'factos/admin.html'

    def lookups(self, request, model_admin):
        return ((None, None),)


    def queryset(self, request, queryset):
        value = request.GET.get('next_download__to_date')
        if value:
            return queryset.filter(next_download__to_date=value)
        
        return queryset