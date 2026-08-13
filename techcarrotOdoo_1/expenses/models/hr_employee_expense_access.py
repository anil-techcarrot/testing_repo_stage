# -*- coding: utf-8 -*-
from odoo import models, fields, api


class HrEmployeeExpenseAccess(models.Model):
    """Adds the 'portal_access_expenses' toggle used by
    employee_self_service_portal's has_feature_access('expenses') check —
    defined here (not in employee_self_service_portal) so this module works
    standalone against an existing ESS install where that field/group were
    left commented out. Syncs to this module's own group_portal_expenses,
    the same pattern ESS uses for its other portal_access_* fields."""
    _inherit = 'hr.employee'

    portal_access_expenses = fields.Boolean(
        "Portal Access Expenses", default=True,
        help="Allow this employee to see and use the Expense Claim Request card in the ESS portal.")

    def write(self, vals):
        res = super().write(vals)
        if 'portal_access_expenses' in vals or 'user_id' in vals:
            self._sync_expense_portal_group()
        return res

    @api.model_create_multi
    def create(self, vals_list):
        employees = super().create(vals_list)
        employees._sync_expense_portal_group()
        return employees

    def _sync_expense_portal_group(self):
        group = self.env.ref('expenses.group_portal_expenses', raise_if_not_found=False)
        if not group:
            return
        for employee in self:
            if not employee.user_id:
                continue
            user = employee.user_id
            if employee.portal_access_expenses:
                user.sudo().write({'group_ids': [(4, group.id)]})
            else:
                user.sudo().write({'group_ids': [(3, group.id)]})
