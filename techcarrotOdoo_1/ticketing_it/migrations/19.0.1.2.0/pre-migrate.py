# -*- coding: utf-8 -*-
"""
Runs automatically before this version's data files are loaded during
`-u ticketing_it` (no manual shell/DB access needed).

The categories, sub-categories and workflow configs that used to be
hardcoded in data/ticket_categories_and_types.xml and data/ticket_type.xml
are still marked noupdate=False in ir_model_data from earlier versions of
this module. As of this version those records are no longer declared in
XML at all (fully user-managed via the UI). Without this step, Odoo's
own end-of-load cleanup would treat them as orphaned and try to delete
them, which fails against the it.ticket.ticket_type_id foreign key.

Flipping noupdate to True here tells Odoo "hands off" before that cleanup
runs, so existing categories/types/workflow-configs are left untouched.
"""


def migrate(cr, version):
    if not version:
        # Fresh install, nothing to migrate.
        return
    cr.execute("""
        UPDATE ir_model_data
        SET noupdate = true
        WHERE module = 'ticketing_it'
          AND model IN ('it.ticket.category', 'it.ticket.type', 'it.ticket.workflow.config')
    """)