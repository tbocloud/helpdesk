# These endpoints lived in helpdesk/api.py, which this package shadowed, so
# "helpdesk.api.<name>" never resolved. Re-exported to keep those paths (used by
# the Support Connection form, HD Form Script and customer sites) working.
from helpdesk.api.support_hub import (  # noqa: F401
    approve_and_execute,
    cancel_session,
    create_pairing_code,
    deregister_client,
    get_action_request_detail,
    get_connections,
    get_login_url,
    get_pending_actions,
    get_remote_audit_log,
    get_session_detail,
    get_sessions,
    get_triage,
    pair_client,
    register_client,
    reject_action_request,
    resume_session,
    rotate_credentials,
    run_triage_now,
    start_investigation,
    ticket_raised,
    view_connection_credentials,
)
