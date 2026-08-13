import base64
import datetime
import io
import logging
import os
import urllib.request

from odoo import models
from PIL import Image, ImageDraw, ImageFont, ImageOps, ImageFilter

_logger = logging.getLogger(__name__)

HR_REVIEWER_GROUP_NAME = 'HR Reviewer'

BACKGROUND_URL = "https://lh3.googleusercontent.com/d/1R_DcmIU6OefuaSdNNS0GOQC60DxSXMwA"


class HrEmployee(models.Model):
    _inherit = 'hr.employee'

    def _cron_send_birthday_notifications(self):
        today = datetime.date.today()
        employees = self.sudo().search([('birthday', '!=', False)])
        birthday_employees = employees.filtered(
            lambda e: e.birthday.day == today.day and e.birthday.month == today.month
        )
        for emp in birthday_employees:
            emp._send_birthday_card_email()

    def _get_hr_reviewer_emails(self):
        group = self.env['res.groups'].sudo().search(
            [('name', '=', HR_REVIEWER_GROUP_NAME)], limit=1
        )
        if not group:
            _logger.warning(
                "Group '%s' not found; no birthday emails will be sent.",
                HR_REVIEWER_GROUP_NAME,
            )
            return []
        emails = [u.email for u in group.user_ids if u.email]
        if not emails:
            _logger.warning(
                "Group '%s' has no users with an email set.", HR_REVIEWER_GROUP_NAME
            )
        return emails

    def _build_birthday_card(self):
        self.ensure_one()

        with urllib.request.urlopen(BACKGROUND_URL) as resp:
            background = Image.open(io.BytesIO(resp.read())).convert('RGBA')
        background = background.resize((2500, 2500))

        if self.image_1920:
            photo = Image.open(io.BytesIO(base64.b64decode(self.image_1920))).convert('RGBA')
            # object-position: top -> anchor the crop to the top of the source photo
            # instead of centering it.
            photo = ImageOps.fit(photo, (560, 650), method=Image.LANCZOS, centering=(0.5, 0.0))

            mask = Image.new('L', (560, 650), 0)
            ImageDraw.Draw(mask).rounded_rectangle([0, 0, 560, 650], radius=10, fill=255)
            background.paste(photo, (395, 770), mask)

        bundled_font = os.path.join(
            os.path.dirname(__file__), '..', 'static', 'fonts', 'DejaVuSans-Bold.ttf'
        )
        # font-family: 'calibri'; font-weight: 700
        font_candidates = [
            r'C:\Windows\Fonts\calibrib.ttf',
            r'C:\Windows\Fonts\arialbd.ttf',
            r'C:\Windows\Fonts\seguisb.ttf',
            '/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf',
            bundled_font,
        ]
        font_path = next((p for p in font_candidates if os.path.exists(p)), None)

        # font-size: 68px
        font_size = 68
        if font_path:
            font = ImageFont.truetype(font_path, font_size)
        else:
            # Should not normally happen since the bundled font ships with the module.
            font = ImageFont.load_default(size=font_size)
            _logger.warning(
                "No TrueType font found (including bundled font); using default font."
            )

        # top: 1340px; left: 1140px
        text_pos = (1140, 1340)

        # text-shadow: 2px 2px 8px rgba(0, 0, 0, 0.6)
        shadow_layer = Image.new('RGBA', background.size, (0, 0, 0, 0))
        ImageDraw.Draw(shadow_layer).text(
            (text_pos[0] + 2, text_pos[1] + 2), self.name, font=font, fill=(0, 0, 0, 153)
        )
        shadow_layer = shadow_layer.filter(ImageFilter.GaussianBlur(8))
        background = Image.alpha_composite(background, shadow_layer)

        # color: white
        ImageDraw.Draw(background).text(text_pos, self.name, font=font, fill=(255, 255, 255, 255))

        output = io.BytesIO()
        background.convert('RGB').save(output, format='PNG')
        return output.getvalue()

    def _send_birthday_card_email(self):
        self.ensure_one()

        hr_emails = self._get_hr_reviewer_emails()
        if not hr_emails:
            return

        try:
            card_bytes = self._build_birthday_card()
        except Exception:
            _logger.exception("Failed to build birthday card for %s", self.name)
            return

        attachment = self.env['ir.attachment'].sudo().create({
            'name': f'birthday_{self.id}.png',
            'datas': base64.b64encode(card_bytes),
            'public': True,
        })
        card_b64 = base64.b64encode(card_bytes).decode('ascii')

        default_mail_server = self.env['ir.mail_server'].sudo().search([('active', '=', True)], limit=1)
        mail = self.env['mail.mail'].sudo().create({
            'subject': f'Happy Birthday - {self.name}',
            'email_from': (
                self.env.company.email
                or self.env.user.email
                or (default_mail_server.smtp_user or False)
            ),
            'email_to': ','.join(hr_emails),
            # Embedding as a data URI (not a /web/image/<id> link) so the card
            # doesn't depend on the recipient being able to reach this server's
            # URL (e.g. localhost during local testing, or a firewalled
            # Odoo.sh instance). Odoo's mail-sending layer automatically
            # converts inline "data:image/..." into a proper CID attachment
            # before it goes out, so it renders in Gmail, Outlook, mobile, etc.
            'body_html': f'<img src="data:image/png;base64,{card_b64}" style="max-width:600px;"/>',
            'attachment_ids': [(6, 0, [attachment.id])],
        })
        mail.send()