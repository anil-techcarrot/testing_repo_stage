# controllers/expense_request.py
import base64
import logging

from odoo import http, fields, _
from odoo.http import request
from odoo.exceptions import AccessError, UserError

_logger = logging.getLogger(__name__)


class ExpenseRequestController(http.Controller):

    # ------------------------------------------------------------------
    # helpers
    # ------------------------------------------------------------------
    def _get_employee(self):
        return request.env['hr.employee'].sudo().search([('user_id', '=', request.env.uid)], limit=1)

    # ------------------------------------------------------------------
    # Create form
    # ------------------------------------------------------------------
    @http.route('/my/ess/expenses/new', type='http', auth='user', website=True)
    def portal_expense_request_new(self, **kw):
        employee = self._get_employee()
        if not employee:
            return request.redirect('/my/ess')

        subcategories = request.env['hr.expense.subcategory'].sudo().search(
            [('active', '=', True)], order='category, sequence, name')
        projects = request.env['project.project'].sudo().search([('active', '=', True)], order='name')

        values = {
            'employee': employee,
            'subcategories': subcategories,
            'projects': projects,
            'page_name': 'ess_dashboard',
            'error': kw.get('error'),
            'error_msg': kw.get('error_msg', ''),
        }
        return request.render('expenses.portal_expense_request_form', values)

    # ------------------------------------------------------------------
    # List (My Expense Claim Requests)
    # ------------------------------------------------------------------
    @http.route(['/my/expenses', '/my/expenses/page/<int:page>'], type='http', auth='user', website=True)
    def portal_my_expense_requests(self, page=1, sortby=None, filterby=None, **kw):
        employee = self._get_employee()
        if not employee:
            return request.redirect('/my/ess')

        domain = [('employee_id', '=', employee.id)]

        searchbar_sortings = {
            'date': {'label': 'Newest First', 'order': 'create_date desc'},
            'name': {'label': 'Reference #', 'order': 'name'},
            'state': {'label': 'Status', 'order': 'state'},
        }
        searchbar_filters = {
            'all': {'label': 'All', 'domain': []},
            'in_progress': {'label': 'In-Progress', 'domain': [('state', '=', 'submitted')]},
            'approved': {'label': 'Approved', 'domain': [('state', 'in', ['approved', 'paid'])]},
            'rejected': {'label': 'Rejected', 'domain': [('state', '=', 'rejected')]},
        }

        if not sortby:
            sortby = 'date'
        if not filterby:
            filterby = 'all'

        order = searchbar_sortings[sortby]['order']
        domain += searchbar_filters[filterby]['domain']

        requests_ = request.env['hr.expense.request'].sudo().search(domain, order=order)

        values = {
            'expense_requests': requests_,
            'page_name': 'expenses',
            'searchbar_sortings': searchbar_sortings,
            'searchbar_filters': searchbar_filters,
            'sortby': sortby,
            'filterby': filterby,
            'employee': employee,
        }
        return request.render('expenses.portal_my_expense_requests', values)

    # ------------------------------------------------------------------
    # Detail (own claim, or an approver reviewing it)
    # ------------------------------------------------------------------
    @http.route(['/my/expenses/<int:request_id>'], type='http', auth='user', website=True)
    def portal_expense_request_detail(self, request_id, **kw):
        employee = self._get_employee()
        expense_request = request.env['hr.expense.request'].sudo().browse(request_id)

        if not expense_request.exists():
            return request.redirect('/my/expenses')

        is_owner = employee and expense_request.employee_id.id == employee.id
        # NOT sudo(): _current_stage_approver_ok() checks self.env.uid against
        # the current stage's approver, so it needs the real logged-in user.
        expense_request_as_user = request.env['hr.expense.request'].browse(request_id)
        is_approver = expense_request_as_user._current_stage_approver_ok() if expense_request.state == 'submitted' else False
        can_mark_paid = expense_request.state == 'approved' and (
            request.env.user.has_group('expenses.group_expense_finance_approver')
            or request.env.user.has_group('expenses.group_expense_cfo_approver'))
        payment_journals = request.env['account.journal'].sudo().search(
            [('type', 'in', ['bank', 'cash'])]) if can_mark_paid else request.env['account.journal']

        if not is_owner and not is_approver and not can_mark_paid and not request.env.user.has_group('base.group_user'):
            return request.redirect('/my/expenses')

        values = {
            'expense_request': expense_request,
            'is_owner': is_owner,
            'is_approver': is_approver,
            'can_mark_paid': can_mark_paid,
            'payment_journals': payment_journals,
            'page_name': 'expenses',
            'employee': employee,
            'error': kw.get('error'),
            'error_msg': kw.get('error_msg', ''),
        }
        return request.render('expenses.portal_expense_request_detail', values)

    # ------------------------------------------------------------------
    # Submit new claim (header + N lines, each with its own optional attachment)
    # ------------------------------------------------------------------
    @http.route('/my/ess/expenses/submit', type='http', auth='user', website=True, methods=['POST'], csrf=True)
    def portal_expense_request_submit(self, **post):
        employee = self._get_employee()
        if not employee:
            return request.redirect('/my/ess')

        form = request.httprequest.form
        files = request.httprequest.files

        expense_category = form.get('expense_category')
        subcategory_id = form.get('subcategory_id')
        currency_code = form.get('currency_code')

        if not expense_category or not subcategory_id or not currency_code:
            return request.redirect('/my/ess/expenses/new?error=1&error_msg=Please+fill+all+required+fields')

        descriptions = form.getlist('line_description[]')
        dates = form.getlist('line_expense_date[]')
        unit_nos = form.getlist('line_unit_no[]')
        unit_amounts = form.getlist('line_unit_amount[]')
        line_attachments = files.getlist('line_attachment[]')

        if not descriptions or not any(d.strip() for d in descriptions):
            return request.redirect('/my/ess/expenses/new?error=1&error_msg=Add+at+least+one+expense+line')

        try:
            vals = {
                'employee_id': employee.id,
                'expense_category': expense_category,
                'subcategory_id': int(subcategory_id),
                'currency_code': currency_code,
                'comments': post.get('comments'),
            }
            if expense_category == 'project_based' and post.get('project_id'):
                vals['project_id'] = int(post.get('project_id'))

            expense_request = request.env['hr.expense.request'].sudo().create(vals)

            for i, desc in enumerate(descriptions):
                if not desc.strip():
                    continue
                line_vals = {
                    'request_id': expense_request.id,
                    'description': desc,
                    'expense_date': dates[i] if i < len(dates) and dates[i] else fields.Date.today(),
                    'unit_no': int(unit_nos[i]) if i < len(unit_nos) and unit_nos[i] else 1,
                    'unit_amount': float(unit_amounts[i]) if i < len(unit_amounts) and unit_amounts[i] else 0.0,
                }
                line = request.env['hr.expense.request.line'].sudo().create(line_vals)

                if i < len(line_attachments) and line_attachments[i] and line_attachments[i].filename:
                    att_file = line_attachments[i]
                    attachment = request.env['ir.attachment'].sudo().create({
                        'name': att_file.filename,
                        'type': 'binary',
                        'datas': base64.b64encode(att_file.read()),
                        'res_model': 'hr.expense.request.line',
                        'res_id': line.id,
                        'mimetype': att_file.mimetype,
                    })
                    line.write({'attachment_id': attachment.id})

            expense_request.action_submit()
            _logger.info("Expense Claim Request %s submitted from ESS portal by %s",
                         expense_request.name, employee.name)
            return request.redirect('/my/expenses/%d?success=1' % expense_request.id)

        except (UserError, ValueError) as e:
            _logger.warning("Error creating Expense Claim Request from ESS portal: %s", e)
            request.env.cr.rollback()
            return request.redirect('/my/ess/expenses/new?error=1&error_msg=%s' % str(e).replace(' ', '+'))
        except Exception as e:
            _logger.error("Error creating Expense Claim Request from ESS portal: %s", e)
            request.env.cr.rollback()
            return request.redirect('/my/ess/expenses/new?error=1&error_msg=Failed+to+submit.+Please+try+again.')

    # ------------------------------------------------------------------
    # Approve / Reject / Mark Paid (acted on from the detail page)
    # ------------------------------------------------------------------
    @http.route('/my/expenses/<int:request_id>/approve', type='http', auth='user', website=True,
                methods=['POST'], csrf=True)
    def portal_expense_request_approve(self, request_id, **post):
        expense_request = request.env['hr.expense.request'].browse(request_id)
        try:
            expense_request.action_approve(comment=post.get('comment'))
        except AccessError as e:
            return request.redirect('/my/expenses/%d?error=1&error_msg=%s' % (request_id, str(e).replace(' ', '+')))
        return request.redirect('/my/expenses/%d' % request_id)

    @http.route('/my/expenses/<int:request_id>/reject', type='http', auth='user', website=True,
                methods=['POST'], csrf=True)
    def portal_expense_request_reject(self, request_id, **post):
        expense_request = request.env['hr.expense.request'].browse(request_id)
        try:
            expense_request.action_reject(comment=post.get('comment'))
        except AccessError as e:
            return request.redirect('/my/expenses/%d?error=1&error_msg=%s' % (request_id, str(e).replace(' ', '+')))
        return request.redirect('/my/expenses/%d' % request_id)

    @http.route('/my/expenses/<int:request_id>/mark-paid', type='http', auth='user', website=True,
                methods=['POST'], csrf=True)
    def portal_expense_request_mark_paid(self, request_id, **post):
        expense_request = request.env['hr.expense.request'].browse(request_id)
        journal_id = post.get('journal_id')
        try:
            expense_request.action_mark_paid(journal_id=int(journal_id) if journal_id else None)
        except (AccessError, UserError) as e:
            return request.redirect('/my/expenses/%d?error=1&error_msg=%s' % (request_id, str(e).replace(' ', '+')))
        return request.redirect('/my/expenses/%d' % request_id)
