from helpdesk.helpdesk.doctype.hd_department.hd_department import set_default_groups


def execute():
    """The owner's two main groups on existing sites: ERP (with GrowthX and
    Internal / R&D) and Digital (with Creative). Only departments not in a group
    yet are changed; new sites get the groups on install."""
    set_default_groups()
