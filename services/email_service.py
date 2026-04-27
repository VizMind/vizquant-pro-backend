"""
Email service using Resend.

Provides helper functions for signup verification and welcome emails.
"""

import logging

import resend

try:
    from backend.config import FRONTEND_URL, RESEND_API_KEY, RESEND_FROM_EMAIL
except ImportError:
    from config import FRONTEND_URL, RESEND_API_KEY, RESEND_FROM_EMAIL

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Logo — served as a static file from the frontend public directory.
# Email clients block base64 data URIs; a plain HTTPS URL is the only
# reliable cross-client approach (Gmail, Apple Mail, Outlook.com, iOS Mail).
# ---------------------------------------------------------------------------

def _logo_img(base_url: str) -> str:
    url = base_url.rstrip("/") + "/logo-horizontal.png"
    return (
        f'<img src="{url}" width="210" height="35" alt="VizQuant" '
        'style="display:block;margin:0 auto;max-width:100%;height:auto;" />'
    )

# ---------------------------------------------------------------------------
# Shared styles (media queries for mobile responsiveness)
# ---------------------------------------------------------------------------

_SHARED_STYLES = """\
<style type="text/css">
  @media only screen and (max-width: 600px) {
    .email-card   { width: 100% !important; border-radius: 0 !important; }
    .email-body   { padding: 28px 20px !important; }
    .email-footer { padding: 20px !important; }
    .feat-td      { display: block !important; width: 100% !important;
                    padding: 4px 0 !important; box-sizing: border-box !important; }
  }
</style>"""

# ---------------------------------------------------------------------------
# Shared email shell (header with logo, gradient accent bar, footer)
# ---------------------------------------------------------------------------

def _email_shell(title: str, content: str, footer_note: str = "") -> str:
    """Wrap content in the standard VizQuant email layout."""
    footer_text = footer_note or (
        "You received this email because an account action was requested for this address.<br/>"
        "您收到此郵件是因為此信箱有帳號相關操作。"
    )
    logo_img = _logo_img(FRONTEND_URL)
    return (
        '<!DOCTYPE html>\n'
        '<html lang="en">\n'
        '<head>\n'
        '  <meta charset="UTF-8" />\n'
        '  <meta name="viewport" content="width=device-width, initial-scale=1.0"/>\n'
        '  <meta http-equiv="X-UA-Compatible" content="IE=edge"/>\n'
        '  <title>' + title + '</title>\n'
        + _SHARED_STYLES + '\n'
        '</head>\n'
        '<body style="margin:0;padding:0;background:#f1f5f9;'
        'font-family:\'Segoe UI\',Roboto,Helvetica,Arial,sans-serif;color:#334155;">\n'
        '\n'
        '  <table width="100%" cellpadding="0" cellspacing="0" role="presentation"\n'
        '         style="background:#f1f5f9;padding:32px 16px;">\n'
        '    <tr>\n'
        '      <td align="center">\n'
        '\n'
        '        <!-- Email card -->\n'
        '        <table class="email-card" width="580" cellpadding="0" cellspacing="0"\n'
        '               role="presentation"\n'
        '               style="background:#ffffff;border-radius:20px;overflow:hidden;\n'
        '                      border:1px solid #e2e8f0;\n'
        '                      box-shadow:0 8px 24px -4px rgba(0,0,0,0.08);">\n'
        '\n'
        '          <!-- Logo header -->\n'
        '          <tr>\n'
        '            <td style="background:#ffffff;padding:36px 40px 28px;text-align:center;">\n'
        + logo_img + '\n'
        '            </td>\n'
        '          </tr>\n'
        '\n'
        '          <!-- Gradient accent bar -->\n'
        '          <tr>\n'
        '            <td style="background:linear-gradient(90deg,#007AFF 0%,#312ECB 100%);\n'
        '                       height:4px;font-size:0;line-height:0;">&nbsp;</td>\n'
        '          </tr>\n'
        '\n'
        '          <!-- Main content -->\n'
        '          <tr>\n'
        '            <td class="email-body" style="padding:40px;">\n'
        + content + '\n'
        '            </td>\n'
        '          </tr>\n'
        '\n'
        '          <!-- Footer -->\n'
        '          <tr>\n'
        '            <td class="email-footer"\n'
        '                style="background:#f8fafc;padding:24px 40px;text-align:center;\n'
        '                       border-top:1px solid #e2e8f0;">\n'
        '              <p style="margin:0 0 8px;font-size:12px;color:#64748b;line-height:1.6;">\n'
        + footer_text + '\n'
        '              </p>\n'
        '              <p style="margin:0;font-size:11px;color:#94a3b8;">\n'
        '                &copy; 2026 VizQuant &nbsp;&middot;&nbsp;\n'
        '                <a href="https://vizquant.com"\n'
        '                   style="color:#007AFF;text-decoration:none;">vizquant.com</a>\n'
        '              </p>\n'
        '            </td>\n'
        '          </tr>\n'
        '\n'
        '        </table>\n'
        '        <!-- /Email card -->\n'
        '\n'
        '      </td>\n'
        '    </tr>\n'
        '  </table>\n'
        '\n'
        '</body>\n'
        '</html>'
    )

# ---------------------------------------------------------------------------
# Verification email
# ---------------------------------------------------------------------------

_VERIFY_CONTENT = """\
<h2 style="margin:0 0 6px;font-size:22px;font-weight:700;color:#1e293b;">
  Confirm your email address
</h2>
<p style="margin:0 0 20px;font-size:14px;color:#64748b;font-weight:500;">
  請驗證您的電子郵件以啟用帳號
</p>

<hr style="border:none;border-top:1px solid #e8edf3;margin:0 0 24px;"/>

<p style="margin:0 0 12px;font-size:15px;line-height:1.7;color:#475569;">
  Thanks for signing up for <strong>VizQuant Pro</strong>.
  Click the button below to verify your email address and start building
  quantitative trading strategies &mdash; <strong>no coding required</strong>.
</p>
<p style="margin:0 0 28px;font-size:13px;line-height:1.7;color:#94a3b8;">
  感謝您註冊 VizQuant Pro。請點擊下方按鈕完成信箱驗證，即可開始建立量化交易策略。
</p>

<table cellpadding="0" cellspacing="0" width="100%" role="presentation">
  <tr>
    <td align="center">
      <a href="{{VERIFY_LINK}}"
         style="display:inline-block;padding:15px 52px;
                background:linear-gradient(90deg,#007AFF 0%,#312ECB 100%);
                color:#ffffff;text-decoration:none;border-radius:12px;
                font-size:15px;font-weight:700;letter-spacing:0.3px;
                box-shadow:0 6px 16px -2px rgba(0,122,255,0.4);">
        Verify Email &nbsp;/&nbsp; 驗證信箱
      </a>
    </td>
  </tr>
</table>

<p style="margin:24px 0 0;font-size:11px;line-height:1.8;color:#94a3b8;
          word-break:break-all;">
  If the button above does not work, copy and paste the link below into your browser:<br/>
  若按鈕無效，請複製以下連結並貼上至瀏覽器：<br/>
  <span style="color:#64748b;">{{VERIFY_LINK}}</span>
</p>"""

_VERIFY_HTML_TEMPLATE = _email_shell(
    title="Verify your VizQuant account",
    content=_VERIFY_CONTENT,
    footer_note=(
        "You received this email because a signup was requested for this address.<br/>"
        "您收到這封信是因為有人使用此信箱在 VizQuant 申請帳號。"
    ),
)

# ---------------------------------------------------------------------------
# Welcome email
# ---------------------------------------------------------------------------

_WELCOME_CONTENT = """\
<h2 style="margin:0 0 6px;font-size:22px;font-weight:700;color:#1e293b;">
  Welcome to VizQuant!
</h2>
<p style="margin:0 0 20px;font-size:14px;color:#64748b;font-weight:500;">
  歡迎加入 VizQuant！
</p>

<hr style="border:none;border-top:1px solid #e8edf3;margin:0 0 24px;"/>

<p style="margin:0 0 12px;font-size:15px;line-height:1.7;color:#475569;">
  Your account is now active. Use our visual block editor to design and backtest
  your own crypto trading strategies &mdash; <strong>no coding required</strong>.
</p>
<p style="margin:0 0 28px;font-size:13px;line-height:1.7;color:#94a3b8;">
  您的帳號已啟用。透過視覺化積木編輯器，輕鬆設計並回測加密貨幣量化交易策略，無需任何程式基礎。
</p>

<!-- Feature tiles -->
<table cellpadding="0" cellspacing="0" width="100%" role="presentation"
       style="margin-bottom:28px;">
  <tr>
    <td class="feat-td" width="33%" style="padding:4px;vertical-align:top;">
      <div style="background:#f0f7ff;border-radius:12px;padding:16px 12px;
                  text-align:center;border:1px solid #dbeafe;">
        <div style="font-size:22px;margin-bottom:6px;">&#128202;</div>
        <div style="font-size:13px;font-weight:700;color:#1e40af;">Backtest</div>
        <div style="font-size:11px;color:#60a5fa;margin-top:2px;">策略回測</div>
      </div>
    </td>
    <td class="feat-td" width="33%" style="padding:4px;vertical-align:top;">
      <div style="background:#f0fdf4;border-radius:12px;padding:16px 12px;
                  text-align:center;border:1px solid #dcfce7;">
        <div style="font-size:22px;margin-bottom:6px;">&#129513;</div>
        <div style="font-size:13px;font-weight:700;color:#166534;">Block Editor</div>
        <div style="font-size:11px;color:#4ade80;margin-top:2px;">積木編輯</div>
      </div>
    </td>
    <td class="feat-td" width="33%" style="padding:4px;vertical-align:top;">
      <div style="background:#fdf4ff;border-radius:12px;padding:16px 12px;
                  text-align:center;border:1px solid #fae8ff;">
        <div style="font-size:22px;margin-bottom:6px;">&#128200;</div>
        <div style="font-size:13px;font-weight:700;color:#6b21a8;">Analytics</div>
        <div style="font-size:11px;color:#c084fc;margin-top:2px;">績效分析</div>
      </div>
    </td>
  </tr>
</table>

<table cellpadding="0" cellspacing="0" width="100%" role="presentation">
  <tr>
    <td align="center">
      <a href="https://vizquant.com"
         style="display:inline-block;padding:15px 52px;
                background:linear-gradient(90deg,#007AFF 0%,#312ECB 100%);
                color:#ffffff;text-decoration:none;border-radius:12px;
                font-size:15px;font-weight:700;letter-spacing:0.3px;
                box-shadow:0 6px 16px -2px rgba(0,122,255,0.4);">
        Get Started &nbsp;/&nbsp; 開始使用
      </a>
    </td>
  </tr>
</table>"""

_WELCOME_HTML = _email_shell(
    title="Welcome to VizQuant Pro",
    content=_WELCOME_CONTENT,
    footer_note=(
        "You received this email because you created an account on VizQuant.<br/>"
        "您收到此郵件是因為您在 VizQuant 建立了帳號。"
    ),
)

# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def send_welcome_email(to_email: str) -> None:
    """Send a welcome email to a newly registered user via Resend."""
    if not RESEND_API_KEY:
        raise RuntimeError("RESEND_API_KEY is not set")
    if not RESEND_FROM_EMAIL:
        raise RuntimeError("RESEND_FROM_EMAIL is not set")

    resend.api_key = RESEND_API_KEY

    params: resend.Emails.SendParams = {
        "from": RESEND_FROM_EMAIL,
        "to": [to_email],
        "subject": "Welcome to VizQuant Pro! 歡迎加入 VizQuant Pro！",
        "html": _WELCOME_HTML,
    }

    response = resend.Emails.send(params)
    logger.info("Welcome email sent to %s (id=%s)", to_email, response.get("id"))


def send_signup_verification_email(to_email: str, verify_link: str) -> None:
    """Send a signup verification email through Resend."""
    if not RESEND_API_KEY:
        raise RuntimeError("RESEND_API_KEY is not set")
    if not RESEND_FROM_EMAIL:
        raise RuntimeError("RESEND_FROM_EMAIL is not set")

    resend.api_key = RESEND_API_KEY

    params: resend.Emails.SendParams = {
        "from": RESEND_FROM_EMAIL,
        "to": [to_email],
        "subject": "Verify your VizQuant Pro account / 請驗證您的 VizQuant Pro 帳號",
        "html": _VERIFY_HTML_TEMPLATE.replace("{{VERIFY_LINK}}", verify_link),
    }

    response = resend.Emails.send(params)
    logger.info(
        "Signup verification email sent to %s (id=%s)",
        to_email,
        response.get("id"),
    )
