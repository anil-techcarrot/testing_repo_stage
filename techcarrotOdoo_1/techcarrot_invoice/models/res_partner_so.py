from odoo import models


class ResPartner(models.Model):
    _inherit = 'res.partner'

    def get_followup_html(self, *args, **kwargs):
        # Call original Odoo method first (keeps all existing overdue/due logic intact)
        html = super(ResPartner, self).get_followup_html(*args, **kwargs)
        if html:
            # Force title change regardless of QWeb template caching
            html = html.replace('Follow-Up Report', 'Statement of Accounts')
            html = html.replace('Follow-up Report', 'Statement of Accounts')
        return html