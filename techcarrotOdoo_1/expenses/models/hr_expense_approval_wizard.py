# -*- coding: utf-8 -*-
from odoo import models, fields, api


class HrExpenseApprovalWizard(models.TransientModel):
    """Small popup so HR / Line Manager / Project Manager / CEO / CFO can
    type a comment or reason when approving or rejecting a claim from the
    Odoo backend — that comment is logged to hr.expense.request.approval
    and is visible to the employee on their portal claim detail page."""
    _name = 'hr.expense.approval.wizard'
    _description = 'Expense Claim Approval Wizard'

    request_id = fields.Many2one('hr.expense.request', string='Expense Claim Request', required=True,
                                  default=lambda self: self.env.context.get('active_id'))
    approval_stage_label = fields.Char(related='request_id.approval_stage_label', string='Pending With', readonly=True)
    comment = fields.Text(string='Comment / Reason',
                           help="Visible to the employee on their claim's Approval Trail.")

    def action_confirm_approve(self):
        self.request_id.action_approve(comment=self.comment)
        return {'type': 'ir.actions.act_window_close'}

    def action_confirm_reject(self):
        self.request_id.action_reject(comment=self.comment)
        return {'type': 'ir.actions.act_window_close'}


class HrExpenseMarkPaidWizard(models.TransientModel):
    """Popup for Finance/CFO to pick which Bank/Cash journal to pay a fully
    approved claim from, when marking it Paid from the Odoo backend."""
    _name = 'hr.expense.mark.paid.wizard'
    _description = 'Expense Claim Mark Paid Wizard'

    request_id = fields.Many2one('hr.expense.request', string='Expense Claim Request', required=True,
                                  default=lambda self: self.env.context.get('active_id'))
    total_amount = fields.Monetary(related='request_id.total_amount', readonly=True)
    currency_id = fields.Many2one(related='request_id.currency_id', readonly=True)
    journal_id = fields.Many2one('account.journal', string='Pay From (Journal)', required=True,
                                  domain="[('type', 'in', ['bank', 'cash'])]")

    def action_confirm_mark_paid(self):
        self.request_id.action_mark_paid(journal_id=self.journal_id.id)
        return {'type': 'ir.actions.act_window_close'}
