# -*- coding: utf-8 -*-
from odoo import models, fields, api


class HrExpenseSubcategory(models.Model):
    """Master data for Expense Sub Categories.
    Mirrors the 'Sub_Category' master list used on the Power Apps portal
    (name, parent category, code, policy text, internal reference).
    """
    _name = 'hr.expense.subcategory'
    _description = 'Expense Sub Category'
    _order = 'category, sequence, name'

    name = fields.Char(string='Sub Category', required=True)
    sequence = fields.Integer(default=10)
    category = fields.Selection([
        ('project_based', 'Project Based'),
        ('non_project_based', 'Non Project Based'),
    ], string='Expense Category', required=True)
    code = fields.Char(string='Code')
    internal_reference = fields.Char(string='Internal Reference')
    policy = fields.Text(string='Policy')
    active = fields.Boolean(default=True)

    _sql_constraints = [
        ('name_category_uniq', 'unique(name, category)',
         'This sub-category already exists for this Expense Category.'),
    ]

    def name_get(self):
        result = []
        for rec in self:
            result.append((rec.id, rec.name))
        return result
