"""Inline HTML email templates for Vocify transactional mail."""

from __future__ import annotations


def _layout(title: str, body_html: str, footer: str = "") -> str:
    return f"""<!DOCTYPE html>
<html>
<head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1"></head>
<body style="margin:0;padding:0;background:#F5F0E8;font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,sans-serif;">
  <table width="100%" cellpadding="0" cellspacing="0" style="background:#F5F0E8;padding:40px 16px;">
    <tr><td align="center">
      <table width="100%" style="max-width:560px;background:#FFFFFF;border-radius:12px;padding:40px 32px;">
        <tr><td>
          <p style="margin:0 0 8px;font-size:11px;font-weight:700;letter-spacing:0.12em;text-transform:uppercase;color:#B8956A;">Vocify</p>
          <h1 style="margin:0 0 20px;font-size:22px;font-weight:600;color:#1A1A1A;">{title}</h1>
          {body_html}
          {footer}
        </td></tr>
      </table>
    </td></tr>
  </table>
</body>
</html>"""


def build_invite_email_html(*, company_name: str, invite_url: str, expires_days: int = 7) -> str:
    body = f"""
<p style="margin:0 0 20px;font-size:15px;line-height:1.6;color:#444;">
  You've been invited to join <strong>{company_name}</strong> on Vocify.
</p>
<p style="margin:0 0 28px;">
  <a href="{invite_url}" style="display:inline-block;background:#B8956A;color:#FFFFFF;text-decoration:none;padding:12px 28px;border-radius:6px;font-size:14px;font-weight:600;">
    Accept invitation
  </a>
</p>
<p style="margin:0 0 12px;font-size:13px;color:#888;background:#F5F0E8;padding:12px;border-radius:6px;word-break:break-all;">
  {invite_url}
</p>
"""
    footer = f'<p style="margin:24px 0 0;font-size:12px;color:#AAA;">This link expires in {expires_days} days.</p>'
    return _layout("You're invited", body, footer)


def build_removed_email_html(*, company_name: str) -> str:
    body = f"""
<p style="margin:0;font-size:15px;line-height:1.6;color:#444;">
  Your access to <strong>{company_name}</strong> on Vocify has been removed.
  If you think this was a mistake, contact your workspace administrator.
</p>
"""
    return _layout("Workspace access removed", body)


def build_password_reset_email_html(*, reset_url: str, expires_hours: int = 1) -> str:
    body = f"""
<p style="margin:0 0 20px;font-size:15px;line-height:1.6;color:#444;">
  Click the button below to reset your Vocify password.
</p>
<p style="margin:0 0 28px;">
  <a href="{reset_url}" style="display:inline-block;background:#B8956A;color:#FFFFFF;text-decoration:none;padding:12px 28px;border-radius:6px;font-size:14px;font-weight:600;">
    Reset password
  </a>
</p>
<p style="margin:0 0 12px;font-size:13px;color:#888;background:#F5F0E8;padding:12px;border-radius:6px;word-break:break-all;">
  {reset_url}
</p>
"""
    footer = f'<p style="margin:24px 0 0;font-size:12px;color:#AAA;">This link expires in {expires_hours} hour(s). If you did not request this, ignore this email.</p>'
    return _layout("Reset your password", body, footer)


def build_password_changed_email_html() -> str:
    body = """
<p style="margin:0;font-size:15px;line-height:1.6;color:#444;">
  Your Vocify password was changed successfully. If you did not make this change, contact support immediately.
</p>
"""
    return _layout("Password changed", body)
