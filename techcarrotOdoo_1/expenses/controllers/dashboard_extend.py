# controllers/dashboard_extend.py
"""Injects Expense Claim Request stats into the existing ESS dashboard data
dict by subclassing employee_self_service_portal's controller and overriding
its internal _get_enhanced_dashboard_data() helper — no file in
employee_self_service_portal is modified. The dashboard template picks these
values up via view inheritance (see views/portal_ess_dashboard_card.xml)."""
from odoo.http import request
from odoo.addons.employee_self_service_portal.controllers.main import PortalEmployee


class ExpenseDashboardExtend(PortalEmployee):

    def _get_enhanced_dashboard_data(self, employee):
        dashboard_data = super()._get_enhanced_dashboard_data(employee)

        expense_requests_count = 0
        expense_requests_pending = 0
        expense_requests_recent = None
        expense_approvals_pending_count = 0
        try:
            expense_requests_count = request.env['hr.expense.request'].search_count([
                ('employee_id', '=', employee.id)
            ])
            expense_requests_pending = request.env['hr.expense.request'].search_count([
                ('employee_id', '=', employee.id),
                ('state', '=', 'submitted')
            ])
            expense_requests_recent = request.env['hr.expense.request'].search([
                ('employee_id', '=', employee.id)
            ], order='create_date desc', limit=3)
            # Requests currently sitting with this user as approver — ir.rule
            # already scopes 'submitted' visibility to the right approver
            # groups / dynamic Project Manager / Line Manager, so a plain
            # count (no sudo) reflects exactly what this user can act on.
            expense_approvals_pending_count = request.env['hr.expense.request'].search_count([
                ('state', '=', 'submitted')
            ])
        except Exception:
            pass

        dashboard_data.update({
            'expense_requests_count': expense_requests_count,
            'expense_requests_pending': expense_requests_pending,
            'expense_requests_recent': expense_requests_recent,
            'expense_approvals_pending_count': expense_approvals_pending_count,
        })
        return dashboard_data
