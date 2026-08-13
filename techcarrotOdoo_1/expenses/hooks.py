# -*- coding: utf-8 -*-


def post_init_hook(env):
    """On install, portal_access_expenses defaults to True for every
    existing employee (Odoo backfills the new column), but the group-sync
    logic in HrEmployeeExpenseAccess only runs on write()/create() — it
    won't fire for that mass backfill. Run it once here so employees who
    already existed before this module was installed get added to
    group_portal_expenses immediately, without needing someone to open and
    re-save each employee record."""
    employees = env['hr.employee'].sudo().search([('user_id', '!=', False)])
    employees._sync_expense_portal_group()
