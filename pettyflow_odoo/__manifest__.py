{
    'name': 'PettyFlow Odoo-Bot',
    'version': '1.0',
    'summary': 'Gestión de recargas de caja menor con bot inteligente',
    'category': 'Operations',
    'author': 'Antigravity / Solenium',
    'depends': ['base', 'mail'],
    'data': [
        'security/ir.model.access.csv',
        'views/petty_reload_views.xml',
    ],
    'installable': True,
    'application': True,
}
