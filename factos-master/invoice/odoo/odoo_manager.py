import xmlrpc.client
from django.conf import settings


class OdooManager:
    
    host = settings.CONFIG_ODOO['HOST']
    db =  settings.CONFIG_ODOO['DATABASE']
    username = settings.CONFIG_ODOO['USERNAME']
    password = settings.CONFIG_ODOO['PASSWORD']
    common = xmlrpc.client.ServerProxy(f'{host}/xmlrpc/2/common')
    models = xmlrpc.client.ServerProxy(uri=f'{host}/xmlrpc/2/object', allow_none=True)

    def authenticate(self):
        try:
            uid = self.common.authenticate(
                self.db,
                self.username,
                self.password,
                {}
            )
            return uid
        except (ConnectionRefusedError, TimeoutError):
            print('ERROR: Odoo connection error.')


class Odoo(OdooManager):


    class DoesNotExist(Exception):
        pass


    def __init__(self, model_name):
        self.model_name = model_name
        self.uid = super().authenticate()


    def info_model(self):

        attrs = super().models.execute_kw(
            super().db,
            self.uid,
            super().password,
            self.model_name,
            'fields_get',
            [], 
            {'attributes': ['string', 'help', 'type', 'relation', 'selection']}
        )
        return attrs


    def call_method(self, method, args):
        attrs = super().models.execute_kw(
            super().db,
            self.uid,
            super().password,
            self.model_name,
            method,
            args,
        )
        return attrs


    def create(self, context):
        """
            Create record.

            Parameters:
                context: Dictionary of partner object

            Returns:
                id (int) of created record
        """
        id = super().models.execute_kw(
            super().db,
            self.uid,
            super().password,
            self.model_name,
            'create',
            [context]
        )
        return id


    def delete(self, ids):
        """
            Delete record.

            Parameters:
                ids: list of ids

            Returns:
                True if register was deleted else False
        """
        return super().models.execute_kw(
            super().db,
            self.uid,
            super().password,
            self.model_name,
            'unlink',
            [ids]
        )


    def filter(self, fields='all', filter=[['id', '!=', -1]], limit=None, extra={}):
        """
            Get matching records

            Parameters:
                fields: list of fields
                filter: list of elements to filter
                limit: maximum number of records to retrieve
        """

        if fields == 'all':
            match = super().models.execute_kw(
                super().db,
                self.uid,
                super().password,
                self.model_name,
                'search_read',
                [filter],
                {
                    'limit': limit,
                    **extra
                },
            )
        else:
            match = super().models.execute_kw(
                super().db,
                self.uid,
                super().password,
                self.model_name,
                'search_read',
                [filter],
                {
                    'fields': fields,
                    'limit': limit,
                    **extra
                },
            )

        return match


    def get(self, fields='all', filter=[['id', '!=', -1]], extra={}):
        try:
            return self.filter(fields=fields, filter=filter, extra=extra, limit=1)[0]
        except IndexError:
            raise self.DoesNotExist(f'No record that matches the given filter exists in the model {self.model_name}')


    def get_id(self, filter):
        return self.get(fields=['id'], filter=filter)['id']


    def count(self, fields='all', filter=[['id', '!=', -1]], extra={}):
        """
            Get model info.

            Parameters:
                fields: list of fields
                filter: list of elements to filter

            https://www.odoo.com/documentation/13.0/reference/orm.html#reference-orm-domains
        """

        if fields == 'all':
            match = super().models.execute_kw(
                super().db,
                self.uid,
                super().password,
                self.model_name,
                'search_count',
                [filter],
                extra
            )
        else:
            match = super().models.execute_kw(
                super().db,
                self.uid,
                super().password,
                self.model_name,
                'search_count',
                [filter],
                {'fields': fields, **extra},
            )

        return match


    def get_by_id(self, id='all', fields='all', filter=['id', '!=', -1]):
        """
            Get record information by id.

            Parameters:
                ids (int or list of ints): Records ids.
                fields: list of fields
                filter: list of elements to filter
            
            https://www.odoo.com/documentation/13.0/reference/orm.html#reference-orm-domains
        """
        if id == 'all':
            id = super().models.execute_kw(
                super().db,
                self.uid,
                super().password,
                self.model_name,
                'search',
                [[filter]]
            )

        if fields == 'all':
            partners = super().models.execute_kw(
                super().db,
                self.uid,
                super().password,
                self.model_name,
                'read',
                [id]
            )
        else:
            partners = super().models.execute_kw(
                super().db,
                self.uid,
                super().password,
                self.model_name,
                'read',
                [id],
                {'fields': fields}
            )

        return partners


    def update(self, ids, context):
        """
            Update record.

            Parameters:
                ids: list of ids
                context: dictionary with attributes to be updated.

            Returns:
                True if register was updated else False
        """
        return super().models.execute_kw(
            super().db,
            self.uid,
            super().password,
            self.model_name,
            'write',
            [ids, context]
        )


    def call_kw(self, id, kw, context={}):
        """
            Calls custom keyword/method.
        """
        return super().models.execute_kw(
            super().db,
            self.uid,
            super().password,
            self.model_name,
            kw,
            [[id]],
            context
        )

