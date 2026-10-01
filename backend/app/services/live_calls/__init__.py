"""Live call awareness: which CRM contact a rep is on the phone with, right now.

The extension reports dialer events it observes on the CRM page, the backend
resolves the contact and fans the call out to the rep's other clients (the
desktop app) over a per-user stream.
"""
