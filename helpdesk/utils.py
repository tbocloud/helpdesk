# Copyright (c) 2026, Quark Cyber Systems FZC and contributors
# For license information, please see license.txt

"""Shared helpers for the QCS Support Hub app."""


def normalize_site_url(raw: str | None) -> str | None:
	"""Normalize a URL entered by an admin.

	Accepts any of the following forms and returns a base URL with scheme
	and no trailing slash:

	    example.com                 -> https://example.com
	    https://example.com         -> https://example.com
	    https://example.com/        -> https://example.com
	    http://customer.localhost:8000/ -> http://customer.localhost:8000
	    qcssupport.localhost        -> http://qcssupport.localhost

	If no scheme is provided, http is used for *.localhost hosts, https otherwise.
	"""
	if not raw:
		return raw
	value = raw.strip().rstrip("/")
	if not value:
		return value
	if "://" in value:
		return value
	host = value.split("/")[0]
	scheme = "http" if "localhost" in host.lower() else "https"
	return f"{scheme}://{value}"
