# -*- coding: utf-8 -*-
from . import models
from . import wizards
from . import controllers


def post_load():
    """
    Monkey-patch PortalEmployee.portal_my_ticket_detail to render our
    standalone template with correct Assigned To and Ticket Progress sections.
    Runs after ALL modules are loaded so PortalEmployee is already defined.
    """
    import logging
    _logger = logging.getLogger(__name__)
    try:
        from odoo.addons.employee_self_service_portal.controllers.main import PortalEmployee
        from odoo.http import request

        def portal_my_ticket_detail(self, ticket_id, **kw):
            employee = request.env['hr.employee'].sudo().search(
                [('user_id', '=', request.env.uid)], limit=1)
            if not employee:
                return request.redirect('/my/ess')

            ticket = request.env['it.ticket'].sudo().search([
                ('id', '=', ticket_id),
                ('employee_id', '=', employee.id),
            ], limit=1)
            if not ticket:
                return request.redirect('/my/tickets')

            attachments = request.env['ir.attachment'].sudo().search([
                ('res_model', '=', 'it.ticket'),
                ('res_id', '=', ticket.id),
            ])

            return request.render('ticketing_it.portal_ticket_detail_it', {
                'ticket': ticket,
                'page_name': 'tickets',
                'ticket_attachments': attachments,
                'employee': employee,
            })

        PortalEmployee.portal_my_ticket_detail = portal_my_ticket_detail
        _logger.info("ticketing_it: patched PortalEmployee.portal_my_ticket_detail")
    except Exception as e:
        _logger.warning("ticketing_it: could not patch portal ticket detail: %s", e)


def post_migrate(cr, registry):
    """Remove duplicate it.ticket.category and it.ticket.type rows."""
    import logging
    _logger = logging.getLogger(__name__)
    try:
        cr.execute("""
            UPDATE it_ticket_type SET category_id = NULL
            WHERE category_id IN (
                SELECT id FROM it_ticket_category
                WHERE id NOT IN (
                    SELECT res_id FROM ir_model_data WHERE model = 'it.ticket.category'
                )
            )
        """)
        cr.execute("""
            DELETE FROM it_ticket_category
            WHERE id NOT IN (
                SELECT res_id FROM ir_model_data WHERE model = 'it.ticket.category'
            )
        """)
        cr.execute("""
            DELETE FROM it_ticket_type
            WHERE id NOT IN (
                SELECT res_id FROM ir_model_data WHERE model = 'it.ticket.type'
            )
            AND id NOT IN (
                SELECT ticket_type_id FROM it_ticket WHERE ticket_type_id IS NOT NULL
            )
        """)
        # Fix stored workflow_level for all existing tickets
        cr.execute("""
            UPDATE it_ticket t
            SET workflow_level = (
                SELECT wc.workflow_level
                FROM it_ticket_workflow_config wc
                WHERE wc.ticket_type_id = t.ticket_type_id
                LIMIT 1
            )
            WHERE t.ticket_type_id IS NOT NULL
        """)
        _logger.info("ticketing_it post_migrate: cleanup done")
    except Exception as e:
        _logger.warning("ticketing_it post_migrate error: %s", e)