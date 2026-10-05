"""Connection from TBO Support to the TBO CRM site (a Frappe CRM site, e.g. tboindia.tbocloud.in).

The hub calls the CRM's REST API with an API key and secret kept in HD CRM Settings.
Today it keeps every active helpdesk agent as a CRM user; fetching the CRM's customers
into helpdesk can build on the same client.
"""
