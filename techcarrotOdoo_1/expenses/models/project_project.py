# -*- coding: utf-8 -*-
from odoo import models, fields, api


class ProjectProject(models.Model):
    """Adds a short reference Code to Odoo's native Project app, so the
    Expense Claim Request's 'Project Code' dropdown can show/select the
    same kind of reference used on the Power Apps portal
    (e.g. GEN/01/00/CM/tcr/SSGPool), while Project Name, Project Manager
    and Line Manager stay driven by the project's own record — no separate
    project master needs to be maintained."""
    _inherit = 'project.project'

    code = fields.Char(string='Project Code', help='Short reference code shown on Expense Claim Requests, '
                                                     'e.g. GEN/01/00/CM/tcr/SSGPool')

    def name_get(self):
        result = []
        for rec in self:
            if rec.code:
                result.append((rec.id, "%s - %s" % (rec.code, rec.name)))
            else:
                result.append((rec.id, rec.name))
        return result

    @api.model
    def _name_search(self, name='', domain=None, operator='ilike', limit=None, order=None):
        domain = domain or []
        if name:
            domain = ['|', ('code', operator, name), ('name', operator, name)] + domain
        return self._search(domain, limit=limit, order=order)
