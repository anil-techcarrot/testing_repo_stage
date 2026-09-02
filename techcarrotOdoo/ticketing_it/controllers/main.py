# -*- coding: utf-8 -*-
from odoo import http, fields
from odoo.http import request
from odoo.addons.web.controllers.home import Home
from werkzeug.utils import redirect as werkzeug_redirect
import logging
import urllib.parse

_logger = logging.getLogger(__name__)


class MicrosoftSSOHome(Home):
    @http.route('/web/session/logout', type='http', auth='none', website=True)
    def logout(self, redirect='/web/login', **kwargs):
        microsoft_logout_url = None
        try:
            uid = request.session.uid
            if uid:
                user = request.env['res.users'].sudo().browse(uid)
                if user.exists() and user.oauth_uid:
                    base_url = request.env['ir.config_parameter'].sudo().get_param('web.base.url')
                    provider = request.env['auth.oauth.provider'].sudo().search(
                        [('id', '=', user.oauth_provider_id.id)], limit=1)
                    tenant_id = 'common'
                    if provider and provider.auth_endpoint:
                        parts = provider.auth_endpoint.split('/')
                        for i, part in enumerate(parts):
                            if 'login.microsoftonline.com' in part and i + 1 < len(parts):
                                tenant_id = parts[i + 1]
                                break
                    microsoft_logout_url = (
                        f"https://login.microsoftonline.com/{tenant_id}/oauth2/v2.0/logout"
                        f"?post_logout_redirect_uri={base_url}/web/login"
                    )
        except Exception as e:
            _logger.error("Azure SSO logout error: %s", e)
        request.session.logout(keep_db=True)
        if microsoft_logout_url:
            return werkzeug_redirect(microsoft_logout_url, code=302)
        return werkzeug_redirect(
            f"{request.httprequest.host_url.rstrip('/')}{redirect}", code=302)


# Import and override PortalEmployee AFTER it is defined
# We do this at import time since controllers/__init__.py imports this file
# after employee_self_service_portal is already loaded (due to depends order)
try:
    from odoo.addons.employee_self_service_portal.controllers.main import PortalEmployee

    class ITTicketPortalOverride(PortalEmployee):
        """
        Override PortalEmployee to render ticketing_it's own ticket detail template.
        This correctly handles all workflow levels (0,1,2,3) with proper
        Assigned To and Ticket Progress sections.
        """

        @http.route(['/my/tickets/<int:ticket_id>'], type='http', auth='user',
                    website=True, sitemap=False)
        def portal_my_ticket_detail(self, ticket_id, **kw):
            employee = request.env['hr.employee'].sudo().search(
                [('user_id', '=', request.env.uid)], limit=1)

            ticket = request.env['it.ticket'].sudo().browse(ticket_id)
            if not ticket.exists():
                return request.redirect('/my/tickets')

            user = request.env.user
            is_owner = bool(employee) and ticket.employee_id.id == employee.id
            is_approver = (
                user == ticket.line_manager_id
                or user == ticket.it_manager_id
                or user.has_group('ticketing_it.group_it_manager')
            )
            if not (is_owner or is_approver):
                return request.redirect('/my/tickets')

            attachments = request.env['ir.attachment'].sudo().search([
                ('res_model', '=', 'it.ticket'),
                ('res_id', '=', ticket.id),
            ])
            for att in attachments:
                if not att.access_token:
                    att.generate_access_token()
            attachments.invalidate_recordset(['access_token'])

            can_approve, can_reject = self._it_ticket_approver_flags(ticket)

            return request.render('ticketing_it.portal_ticket_detail_it', {
                'ticket': ticket,
                'page_name': 'tickets',
                'ticket_attachments': attachments,
                'employee': employee,
                'can_approve': can_approve,
                'can_reject': can_reject,
                'error': kw.get('error'),
                'error_message': kw.get('error_msg', ''),
            })

        # ── Helpers ──────────────────────────────────────────────────────

        def _it_ticket_approver_flags(self, ticket):
            """Return (can_approve, can_reject) for the CURRENT portal user on this ticket.
            Only Line Manager and IT Manager can act from the portal — HR approval
            stays backend-only, same as before."""
            user = request.env.user
            state = ticket.state
            if state == 'manager_approval':
                ok = bool(ticket.line_manager_id) and user == ticket.line_manager_id
            elif state == 'it_approval':
                ok = user.has_group('ticketing_it.group_it_manager')
            else:
                ok = False
            return ok, ok

        def _it_ticket_pending_for_user(self):
            """Tickets currently awaiting approval from the logged-in portal user,
            as either Line Manager or IT Manager (HR approval is backend-only)."""
            user = request.env.user
            domain = ['|',
                       '&', ('state', '=', 'manager_approval'), ('line_manager_id', '=', user.id),
                       '&', ('state', '=', 'it_approval'), ('it_manager_id', '=', user.id)]
            return request.env['it.ticket'].sudo().search(domain, order='create_date desc')

        def _it_ticket_approved_for_user(self, limit=50):
            """Tickets this user has approved — as Line Manager (manager_approval_date
            is set) or as IT Manager (it_approval_date is set) — regardless of what
            state the ticket has since moved to. Explicitly excludes rejected tickets,
            since the approval-date fields get stamped on rejection too (they just mark
            the ticket leaving that approval stage, not a positive decision)."""
            user = request.env.user
            domain = [
                ('state', '!=', 'rejected'),
                '|',
                '&', ('manager_approval_date', '!=', False), ('line_manager_id', '=', user.id),
                '&', ('it_approval_date', '!=', False), ('it_manager_id', '=', user.id),
            ]
            return request.env['it.ticket'].sudo().search(domain, order='write_date desc', limit=limit)

        def _it_ticket_rejected_for_user(self, limit=50):
            """Tickets this user rejected, as Line Manager or IT Manager."""
            user = request.env.user
            domain = [
                ('state', '=', 'rejected'),
                '|',
                ('line_manager_id', '=', user.id),
                ('it_manager_id', '=', user.id),
            ]
            return request.env['it.ticket'].sudo().search(domain, order='write_date desc', limit=limit)

        def _it_ticket_is_approver_anywhere(self):
            """True if this portal user is a Line Manager or IT Manager — either by
            security group membership (so the page is discoverable even before any
            ticket exists) or because a real ticket currently lists them as the
            line manager — used to gate access to the /my/it-approvals page."""
            user = request.env.user
            if user.has_group('ticketing_it.group_it_manager'):
                return True
            if user.has_group('ticketing_it.group_line_manager'):
                return True
            return request.env['it.ticket'].sudo().search_count(
                [('line_manager_id', '=', user.id)]) > 0

        # ── Approvals list page ──────────────────────────────────────────

        @http.route(['/my/it-approvals'], type='http', auth='user', website=True)
        def portal_it_ticket_approvals(self, filterby=None, **kw):
            if not self._it_ticket_is_approver_anywhere():
                return request.redirect('/my/ess')

            _logger.info("IT-APPROVALS DEBUG: raw filterby param = %r, user=%s",
                         filterby, request.env.user.login)

            if not filterby:
                filterby = 'pending'

            if filterby == 'approved':
                tickets = self._it_ticket_approved_for_user()
            elif filterby == 'rejected':
                tickets = self._it_ticket_rejected_for_user()
            else:
                filterby = 'pending'
                tickets = self._it_ticket_pending_for_user()

            _logger.info("IT-APPROVALS DEBUG: resolved filterby=%s, ticket_count=%s, ids=%s",
                         filterby, len(tickets), tickets.ids)

            success_message = None
            if kw.get('success') == 'approved':
                success_message = 'Ticket approved successfully.'
            elif kw.get('success') == 'rejected':
                success_message = 'Ticket rejected.'

            return request.render('ticketing_it.portal_it_ticket_approvals', {
                'tickets': tickets,
                'filterby': filterby,
                'page_name': 'it_approvals',
                'success_message': success_message,
                'error': kw.get('error'),
                'error_message': kw.get('error_msg', ''),
            })

        # ── Approve / Reject actions ─────────────────────────────────────

        @http.route(['/my/tickets/<int:ticket_id>/portal-approve'], type='http',
                    auth='user', website=True, methods=['POST'], csrf=True)
        def portal_it_ticket_approve(self, ticket_id, **kw):
            ticket = request.env['it.ticket'].sudo().browse(ticket_id)
            if not ticket.exists():
                return request.redirect('/my/it-approvals')

            can_approve, _can_reject = self._it_ticket_approver_flags(ticket)
            if not can_approve:
                return request.redirect(
                    '/my/tickets/%d?error=1&error_msg=%s' % (
                        ticket_id,
                        urllib.parse.quote_plus(
                            "You are not authorised to approve this ticket, "
                            "or it is no longer pending your approval."
                        ),
                    )
                )

            comment = (kw.get('comment') or '').strip()
            redirect_to = kw.get('redirect_to') or '/my/it-approvals?success=approved'

            try:
                wizard = request.env['it.ticket.approve.wizard'].sudo().create({
                    'ticket_id': ticket.id,
                    'comment': comment,
                })
                wizard.approve_ticket()
                return request.redirect(redirect_to)
            except Exception as e:
                _logger.error("Portal IT ticket approve failed for ticket %s: %s", ticket_id, e)
                request.env.cr.rollback()
                return request.redirect(
                    '/my/tickets/%d?error=1&error_msg=%s' % (
                        ticket_id,
                        urllib.parse.quote_plus(
                            "Could not approve this ticket. Please try again or contact IT."
                        ),
                    )
                )

        @http.route(['/my/tickets/<int:ticket_id>/portal-reject'], type='http',
                    auth='user', website=True, methods=['POST'], csrf=True)
        def portal_it_ticket_reject(self, ticket_id, **kw):
            ticket = request.env['it.ticket'].sudo().browse(ticket_id)
            if not ticket.exists():
                return request.redirect('/my/it-approvals')

            _can_approve, can_reject = self._it_ticket_approver_flags(ticket)
            if not can_reject:
                return request.redirect(
                    '/my/tickets/%d?error=1&error_msg=%s' % (
                        ticket_id,
                        urllib.parse.quote_plus(
                            "You are not authorised to reject this ticket, "
                            "or it is no longer pending your approval."
                        ),
                    )
                )

            reason = (kw.get('rejection_reason') or '').strip()
            if not reason:
                return request.redirect(
                    '/my/tickets/%d?error=1&error_msg=%s' % (
                        ticket_id,
                        urllib.parse.quote_plus("Please provide a rejection reason."),
                    )
                )

            redirect_to = kw.get('redirect_to') or '/my/it-approvals?success=rejected'

            try:
                ticket.sudo().do_reject(reason)
                return request.redirect(redirect_to)
            except Exception as e:
                _logger.error("Portal IT ticket reject failed for ticket %s: %s", ticket_id, e)
                request.env.cr.rollback()
                return request.redirect(
                    '/my/tickets/%d?error=1&error_msg=%s' % (
                        ticket_id,
                        urllib.parse.quote_plus(
                            "Could not reject this ticket. Please try again or contact IT."
                        ),
                    )
                )

    _logger.info("ticketing_it: ITTicketPortalOverride registered successfully")

except ImportError as e:
    _logger.warning("ticketing_it: could not override portal ticket detail: %s", e)