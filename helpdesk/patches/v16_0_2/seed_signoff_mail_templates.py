from helpdesk.helpdesk.doctype.hd_signoff_template.hd_signoff_template import (
    ensure_default_signoff_templates,
)


def execute():
    # the UAT templates with their mail (docs/project-signoff.md, Mail); a site's own
    # templates are left as they are
    ensure_default_signoff_templates()
