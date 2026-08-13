# -*- coding: utf-8 -*-
"""
Expense Claim Request — custom model backing the ESS portal "Expense Claim
Request" card. Built to mirror the Power Apps flow:

    Non Project Based  ->  HR  ->  Finance Executive  ->  CFO
    Project Based      ->  Project Manager  ->  Line Manager  ->  CEO  ->  CFO

    (Project Based claims do NOT go through HR — only Non Project Based
    claims require HR approval, per explicit confirmation.)

NOTE ON APPROVAL CHAIN — please confirm before go-live:
  * The Non Project Based chain above (HR -> Finance Executive -> CFO) is
    taken from the actual approval audit trail captured in the Power Apps
    screenshots supplied. Earlier verbal notes said "HR -> CEO -> CFO" —
    if CEO really is a stage (e.g. above a value threshold, or CEO/Finance
    Executive is the same person wearing two hats), update EXPENSE_WORKFLOWS
    below accordingly.
Both chains are declared in one place (EXPENSE_WORKFLOWS) below, so they are
easy to reorder if needed.
"""
from odoo import models, fields, api, _
from odoo.exceptions import UserError, AccessError

EXPENSE_WORKFLOWS = {
    'non_project_based': [
        ('hr', 'HR', 'expenses.group_expense_hr_approver'),
        ('finance_executive', 'Finance Executive', 'expenses.group_expense_finance_approver'),
        ('cfo', 'CFO', 'expenses.group_expense_cfo_approver'),
    ],
    'project_based': [
        ('project_manager', 'Project Manager', None),   # dynamic: project_id.user_id
        ('line_manager', 'Line Manager', None),          # dynamic: employee_id.parent_id.user_id
        # No HR stage for Project Based claims — confirmed by the requester:
        # only Non Project Based claims need HR approval.
        ('ceo', 'CEO', 'expenses.group_expense_ceo_approver'),
        ('cfo', 'CFO', 'expenses.group_expense_cfo_approver'),
    ],
}

CURRENCY_SELECTION = [
    ('AED', 'AED'), ('INR', 'INR'), ('PKR', 'PKR'), ('BHD', 'BHD'), ('USD', 'USD'),
]


class HrExpenseRequest(models.Model):
    _name = 'hr.expense.request'
    _description = 'Expense Claim Request'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'create_date desc'

    name = fields.Char(string='Reference #', copy=False, readonly=True, default=lambda self: _('New'))
    employee_id = fields.Many2one('hr.employee', string='Employee', required=True,
                                   default=lambda self: self.env['hr.employee'].sudo().search(
                                       [('user_id', '=', self.env.uid)], limit=1))
    emp_code = fields.Char(related='employee_id.employee_id', string='Emp Code', store=True)

    expense_category = fields.Selection([
        ('project_based', 'Project Based'),
        ('non_project_based', 'Non Project Based'),
    ], string='Expense Category', required=True, default='non_project_based', tracking=True)

    subcategory_id = fields.Many2one('hr.expense.subcategory', string='Expense Sub Category', required=True,
                                      domain="[('category', '=', expense_category)]")
    policy = fields.Text(related='subcategory_id.policy', string='Policy', readonly=True)

    currency_code = fields.Selection(CURRENCY_SELECTION, string='Currency', required=True, default='AED')

    # Project Based only
    project_id = fields.Many2one('project.project', string='Project Code',
                                  domain="[('active', '=', True)]")
    project_name = fields.Char(related='project_id.name', string='Project Name', readonly=True)
    project_manager_id = fields.Many2one('res.users', string='Project Manager',
                                          compute='_compute_project_manager', store=True)
    line_manager_id = fields.Many2one('res.users', string='Line Manager',
                                       compute='_compute_line_manager', store=True)

    line_ids = fields.One2many('hr.expense.request.line', 'request_id', string='Expense Lines', copy=True)
    comments = fields.Text(string='Comments')
    total_amount = fields.Monetary(string='Total Expense Amount', compute='_compute_total_amount', store=True,
                                    currency_field='currency_id')
    currency_id = fields.Many2one('res.currency', compute='_compute_currency_id', store=True)

    state = fields.Selection([
        ('draft', 'Draft'),
        ('submitted', 'In-Progress'),
        ('rejected', 'Rejected'),
        ('approved', 'Approved'),
        ('paid', 'Paid'),
        ('cancelled', 'Cancelled'),
    ], string='Status', default='draft', tracking=True, copy=False)

    approval_stage = fields.Char(string='Current Approval Stage', copy=False, readonly=True,
                                  help="Technical key of the stage currently pending action, "
                                       "e.g. 'hr', 'finance_executive', 'cfo'.")
    approval_stage_label = fields.Char(string='Pending With', compute='_compute_approval_stage_label', store=True)

    submitted_date = fields.Datetime(string='Submitted Date', readonly=True, copy=False)
    approval_ids = fields.One2many('hr.expense.request.approval', 'request_id', string='Approval Trail')

    # Accounting integration — set when Finance/CFO marks the request Paid.
    payment_id = fields.Many2one('account.payment', string='Payment Entry', readonly=True, copy=False)
    payment_journal_id = fields.Many2one('account.journal', string='Paid From (Journal)', readonly=True, copy=False)
    payment_move_id = fields.Many2one('account.move', related='payment_id.move_id', string='Journal Entry', readonly=True)
    payment_state = fields.Selection(related='payment_id.state', string='Payment Status', readonly=True)

    # ------------------------------------------------------------------
    # Computes
    # ------------------------------------------------------------------
    @api.depends('line_ids.expense_amount')
    def _compute_total_amount(self):
        for rec in self:
            rec.total_amount = sum(rec.line_ids.mapped('expense_amount'))

    @api.depends('currency_code')
    def _compute_currency_id(self):
        for rec in self:
            rec.currency_id = self.env['res.currency'].sudo().search([('name', '=', rec.currency_code)], limit=1)

    @api.depends('project_id')
    def _compute_project_manager(self):
        for rec in self:
            rec.project_manager_id = rec.project_id.user_id if rec.project_id else False

    @api.depends('employee_id')
    def _compute_line_manager(self):
        for rec in self:
            rec.line_manager_id = rec.employee_id.parent_id.user_id if rec.employee_id.parent_id else False

    @api.depends('state', 'approval_stage', 'expense_category')
    def _compute_approval_stage_label(self):
        for rec in self:
            if rec.state != 'submitted' or not rec.approval_stage:
                rec.approval_stage_label = ''
                continue
            workflow = EXPENSE_WORKFLOWS.get(rec.expense_category, [])
            label = dict((k, l) for k, l, _g in workflow).get(rec.approval_stage, rec.approval_stage)
            rec.approval_stage_label = label

    # ------------------------------------------------------------------
    # Create / sequence
    # ------------------------------------------------------------------
    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get('name', _('New')) == _('New'):
                vals['name'] = self.env['ir.sequence'].next_by_code('hr.expense.request') or _('New')
        return super().create(vals_list)

    # ------------------------------------------------------------------
    # Workflow
    # ------------------------------------------------------------------
    def action_submit(self):
        for rec in self:
            if not rec.line_ids:
                raise UserError(_('Add at least one expense line before submitting.'))
            workflow = EXPENSE_WORKFLOWS.get(rec.expense_category)
            if not workflow:
                raise UserError(_('No approval workflow configured for this Expense Category.'))
            first_stage = workflow[0][0]
            rec.write({
                'state': 'submitted',
                'approval_stage': first_stage,
                'submitted_date': fields.Datetime.now(),
            })
            rec._log_approval_step(first_stage, 'submitted', self.env.user, _('Request submitted.'))
        return True

    def _current_stage_approver_ok(self):
        """Return True if the current user is allowed to act on this record's current stage."""
        self.ensure_one()
        workflow = EXPENSE_WORKFLOWS.get(self.expense_category, [])
        stage_map = {k: (label, group) for k, label, group in workflow}
        stage = stage_map.get(self.approval_stage)
        if not stage:
            return False
        _label, group_xmlid = stage
        # Dynamic stages: Project Manager / Line Manager
        if self.approval_stage == 'project_manager':
            return bool(self.project_manager_id) and self.project_manager_id.id == self.env.uid
        if self.approval_stage == 'line_manager':
            return bool(self.line_manager_id) and self.line_manager_id.id == self.env.uid
        # Group-based stages
        if group_xmlid:
            return self.env.user.has_group(group_xmlid)
        return False

    def action_approve(self, comment=None):
        for rec in self:
            if rec.state != 'submitted':
                raise UserError(_('Only submitted requests can be approved.'))
            if not rec._current_stage_approver_ok():
                raise AccessError(_('You are not the approver for the current stage of this request.'))
            workflow = EXPENSE_WORKFLOWS.get(rec.expense_category, [])
            keys = [k for k, _l, _g in workflow]
            idx = keys.index(rec.approval_stage)
            rec._log_approval_step(rec.approval_stage, 'approved', self.env.user, comment or '')
            if idx + 1 < len(keys):
                rec.write({'approval_stage': keys[idx + 1]})
            else:
                rec.write({'state': 'approved', 'approval_stage': False})
        return True

    def action_reject(self, comment=None):
        for rec in self:
            if rec.state != 'submitted':
                raise UserError(_('Only submitted requests can be rejected.'))
            if not rec._current_stage_approver_ok():
                raise AccessError(_('You are not the approver for the current stage of this request.'))
            rec._log_approval_step(rec.approval_stage, 'rejected', self.env.user, comment or '')
            rec.write({'state': 'rejected'})
        return True

    def action_mark_paid(self, journal_id=None):
        """Finance/CFO marks a fully-approved request as Paid. This creates
        and posts an account.payment (outbound, to the employee) against the
        chosen Bank/Cash journal — this is what actually deducts the amount
        from that journal's balance and shows up as a journal entry in
        Accounting, rather than just flipping a status label."""
        for rec in self:
            if rec.state != 'approved':
                raise UserError(_('Only fully approved requests can be marked Paid.'))
            if not (self.env.user.has_group('expenses.group_expense_finance_approver')
                    or self.env.user.has_group('expenses.group_expense_cfo_approver')):
                raise AccessError(_('Only Finance or CFO can mark a request as Paid.'))
            if not journal_id:
                raise UserError(_('Please select which Bank/Cash journal this is being paid from.'))

            journal = self.env['account.journal'].sudo().browse(journal_id)
            if not journal.exists() or journal.type not in ('bank', 'cash'):
                raise UserError(_('Please select a valid Bank or Cash journal.'))

            partner = rec._get_payment_partner()

            payment = self.env['account.payment'].sudo().create({
                'payment_type': 'outbound',
                'partner_type': 'supplier',
                'partner_id': partner.id,
                'amount': rec.total_amount,
                'currency_id': rec.currency_id.id,
                'journal_id': journal.id,
                'date': fields.Date.context_today(rec),
                'ref': _('Expense Claim %s - %s') % (rec.name, rec.subcategory_id.name),
            })
            payment.action_post()

            rec.write({
                'state': 'paid',
                'payment_id': payment.id,
                'payment_journal_id': journal.id,
            })
            rec._log_approval_step(
                'paid', 'paid', self.env.user,
                _('Marked as Paid. Payment %s posted to journal %s (Journal Entry: %s).') % (
                    payment.name, journal.name, payment.move_id.name if payment.move_id else '-')
            )
        return True

    def _get_payment_partner(self):
        """Resolve the res.partner to pay for this employee's reimbursement.
        Tries the fields Odoo commonly uses across versions, in order."""
        self.ensure_one()
        employee = self.employee_id
        partner = (
            getattr(employee, 'work_contact_id', False)
            or getattr(employee, 'address_home_id', False)
            or (employee.user_id and employee.user_id.partner_id)
        )
        if not partner:
            raise UserError(_(
                'No contact record is linked to employee %s, so a payment cannot be created. '
                'Set a Work Contact / Home Address on the employee record first.'
            ) % employee.name)
        return partner

    def action_cancel(self):
        for rec in self:
            if rec.state not in ('draft', 'submitted'):
                raise UserError(_('Only draft or in-progress requests can be cancelled.'))
            rec.write({'state': 'cancelled'})
        return True

    def _log_approval_step(self, role, action_type, user, comment):
        self.ensure_one()
        workflow = EXPENSE_WORKFLOWS.get(self.expense_category, [])
        label = dict((k, l) for k, l, _g in workflow).get(role, role.replace('_', ' ').title())
        self.env['hr.expense.request.approval'].sudo().create({
            'request_id': self.id,
            'role': label,
            'action_taker_id': user.id,
            'action_type': action_type,
            'comments': comment,
        })


class HrExpenseRequestLine(models.Model):
    _name = 'hr.expense.request.line'
    _description = 'Expense Claim Request Line'

    request_id = fields.Many2one('hr.expense.request', string='Request', required=True, ondelete='cascade')
    description = fields.Char(string='Description', required=True)
    expense_date = fields.Date(string='Expense Date', required=True, default=fields.Date.context_today)
    unit_no = fields.Integer(string='Unit No', default=1)
    unit_amount = fields.Float(string='Unit Amount', required=True)
    expense_amount = fields.Float(string='Expense', compute='_compute_expense_amount', store=True)
    attachment_id = fields.Many2one('ir.attachment', string='Attachment')

    @api.depends('unit_no', 'unit_amount')
    def _compute_expense_amount(self):
        for rec in self:
            rec.expense_amount = (rec.unit_no or 0) * (rec.unit_amount or 0.0)


class HrExpenseRequestApproval(models.Model):
    _name = 'hr.expense.request.approval'
    _description = 'Expense Claim Request Approval Trail'
    _order = 'create_date asc'

    request_id = fields.Many2one('hr.expense.request', string='Request', required=True, ondelete='cascade')
    role = fields.Char(string='Role')
    action_taker_id = fields.Many2one('res.users', string='Action Taker')
    action_type = fields.Selection([
        ('submitted', 'Request Submitted'),
        ('approved', 'Approved'),
        ('rejected', 'Rejected'),
        ('paid', 'Paid'),
    ], string='Action Type')
    comments = fields.Text(string='Comments')
    action_date = fields.Datetime(string='Date and Time', default=fields.Datetime.now)
