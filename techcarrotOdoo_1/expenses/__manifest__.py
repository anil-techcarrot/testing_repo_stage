# -*- coding: utf-8 -*-
{
    "name": "Expenses - Expense Claim Request",
    "version": "19.0.1.0.0",
    "summary": "Expense Claim Request workflow (Project Based / Non Project Based) with portal card, "
               "multi-stage approvals, and Accounting payment posting.",
    "description": """
Expense Claim Request
======================
Standalone module implementing the Expense Claim Request feature shown on the
Employee Self Service (ESS) portal dashboard, replicating the Power Apps flow:

* Non Project Based  -> HR -> Finance Executive -> CFO
* Project Based      -> Project Manager -> Line Manager -> HR -> CEO -> CFO

Includes:
* hr.expense.subcategory master data (21 sub-categories with policy text)
* hr.expense.request / .line / .approval models with a configurable approval chain
* Portal pages (create / list / detail) under /my/expenses
* A dashboard card injected into the ESS enhanced dashboard
* Backend list/form views + menu for internal users (status, pending-with, approval trail)
* Approve / Reject / Mark-as-Paid wizards (captures a comment visible to the employee)
* Accounting integration: Mark as Paid posts a real account.payment against a chosen
  Bank/Cash journal

Depends on employee_self_service_portal only for: the portal_access_expenses toggle
on hr.employee, the /my/ess dashboard template it injects a card into, and the
portal layout/helpers it reuses. No employee_self_service_portal file is modified —
integration is done entirely through view inheritance and controller subclassing.
""",
    "depends": ["employee_self_service_portal", "hr_expense", "account", "project", "portal"],
    "category": "Human Resources",
    "author": "Lovaraju Mylapalli",
    "data": [
        "security/expense_security.xml",
        "security/ir.model.access.csv",
        "data/hr_expense_request_sequence.xml",
        "data/hr_expense_subcategory_data.xml",
        "views/hr_expense_approval_wizard_views.xml",
        "views/hr_expense_request_backend_views.xml",
        "views/portal_expense_request_form.xml",
        "views/portal_expense_request_list.xml",
        "views/portal_expense_request_detail.xml",
        "views/portal_ess_dashboard_card.xml",
    ],
    "installable": True,
    "application": True,
    "auto_install": False,
    "post_init_hook": "post_init_hook",
    "license": "LGPL-3",
}
