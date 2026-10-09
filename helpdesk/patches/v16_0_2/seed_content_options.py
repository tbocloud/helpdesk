from helpdesk.content_options import ensure_default_content_options


def execute():
    """Platforms and post types are records now; existing sites get today's options."""
    ensure_default_content_options()
