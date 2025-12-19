"""
WhatsApp Cloud API wrapper using pywa library.
"""

import json
import logging
import re
from typing import Optional

import openpyxl
from pywa import WhatsApp
from pywa.types.templates import BodyText, TemplateStatus

logger = logging.getLogger(__name__)

# Cache for WhatsApp client instances
_clients: dict[str, WhatsApp] = {}


def _get_client(phone_id: str, token: str, waba_id: str = None) -> WhatsApp:
    """Get or create a cached WhatsApp client instance."""
    key = f"{phone_id}:{token[:10]}"
    if key not in _clients:
        _clients[key] = WhatsApp(
            phone_id=phone_id,
            token=token,
            business_account_id=waba_id,
            api_version=24.0,
        )
    return _clients[key]


def generate_components(texts_list: list) -> Optional[BodyText]:
    """
    Generate body text params for WhatsApp template.

    Args:
        texts_list: List of text values for template body parameters

    Returns:
        BodyText params object or None if no texts
    """
    filtered = [str(t) for t in texts_list if t]
    return BodyText.params(*filtered) if filtered else None


def send_whatsapp_message(
    WHATSAPP_PHONE_NUMBER_ID: str,
    WHATSAPP_ACCESS_TOKEN: str,
    template_name: str,
    language_code: str,
    country_code: str,
    phone_number: str,
    components: Optional[list] = None,
) -> dict:
    """
    Send a WhatsApp template message.

    Args:
        WHATSAPP_PHONE_NUMBER_ID: WhatsApp Phone Number ID
        WHATSAPP_ACCESS_TOKEN: WhatsApp Access Token
        template_name: Name of the approved template
        language_code: Template language code (e.g., 'en', 'en_US')
        country_code: Country code for phone number
        phone_number: Recipient phone number (without country code)
        components: List of pywa params (BodyText.params, HeaderImage.params, etc.)

    Returns:
        Dict with 'status_code' and 'response' keys
    """
    client = _get_client(WHATSAPP_PHONE_NUMBER_ID, WHATSAPP_ACCESS_TOKEN)
    full_phone = f"{country_code}{phone_number}"

    # Convert string language code to TemplateLanguage enum
    from pywa.types.templates import TemplateLanguage

    try:
        language = TemplateLanguage(language_code)
    except ValueError:
        language = language_code  # Fallback to string if not in enum

    logger.info(f"Sending '{template_name}' to {full_phone}, lang={language}")

    try:
        result = client.send_template(
            to=full_phone,
            name=template_name,
            language=language,
            params=components,
        )

        logger.info(f"Message sent: {result.id}")
        return {
            "status_code": 200,
            "response": json.dumps(
                {
                    "messaging_product": "whatsapp",
                    "contacts": [{"wa_id": full_phone}],
                    "messages": [{"id": result.id}],
                }
            ),
        }

    except Exception as e:
        logger.error(f"Send failed: {e}")
        raise


def get_message_templates(
    WHATSAPP_BUSINESS_ACCOUNT_ID: str, WHATSAPP_ACCESS_TOKEN: str
) -> dict:
    """
    Get approved message templates from WhatsApp Business Account.

    Returns:
        Dict mapping template names to template details
    """
    client = WhatsApp(
        token=WHATSAPP_ACCESS_TOKEN,
        business_account_id=WHATSAPP_BUSINESS_ACCOUNT_ID,
        api_version=24.0,
    )

    templates = {}
    for t in client.get_templates(statuses=[TemplateStatus.APPROVED]):
        # Convert pywa template to dict format expected by app.py
        components = []
        if hasattr(t, "components") and t.components:
            for comp in t.components:
                comp_dict = {
                    "type": (
                        comp.type.value
                        if hasattr(comp.type, "value")
                        else str(comp.type)
                    )
                }
                if hasattr(comp, "text") and comp.text:
                    comp_dict["text"] = comp.text
                if hasattr(comp, "format") and comp.format:
                    comp_dict["format"] = (
                        comp.format.value
                        if hasattr(comp.format, "value")
                        else str(comp.format)
                    )
                if hasattr(comp, "example") and comp.example:
                    # pywa returns example as tuple, convert to API format {"body_text": [[...]]}
                    example = comp.example
                    if isinstance(example, (tuple, list)) and len(example) > 0:
                        comp_dict["example"] = {"body_text": [list(example)]}
                    else:
                        comp_dict["example"] = example
                components.append(comp_dict)

        templates[t.name] = {
            "status": t.status.value if hasattr(t.status, "value") else t.status,
            "components": components,
            "language": (
                t.language.value if hasattr(t.language, "value") else t.language
            ),
        }

    return templates


def upload_media(
    WHATSAPP_PHONE_NUMBER_ID: str,
    WHATSAPP_ACCESS_TOKEN: str,
    file_bytes: bytes,
    file_type: str,
) -> str:
    """
    Upload media to WhatsApp.

    Returns:
        JSON string with media upload response
    """
    ext_map = {
        "image/jpeg": ".jpeg",
        "image/jpg": ".jpeg",
        "image/png": ".png",
        "video/mp4": ".mp4",
        "video/3gpp": ".3gp",
    }

    if file_type not in ext_map:
        raise ValueError(f"Unsupported file type: {file_type}")

    client = _get_client(WHATSAPP_PHONE_NUMBER_ID, WHATSAPP_ACCESS_TOKEN)

    media = client.upload_media(
        media=file_bytes,
        mime_type=file_type,
        filename=f"media{ext_map[file_type]}",
    )

    return json.dumps({"id": media.id})


def excel_to_phone_list(file_path) -> dict:
    """
    Read phone numbers from Excel file.

    Returns:
        Dict mapping sheet names to lists of phone numbers
    """
    result = {}
    mobile_pattern = re.compile(r"(mobile|phone|cell|tel|contact)", re.I)
    valid_pattern = re.compile(r"^\d{10}$")

    wb = openpyxl.load_workbook(file_path)
    for sheet in wb.worksheets:
        for column in sheet.iter_cols(min_row=1, max_row=sheet.max_row):
            header = column[0].value
            if header and mobile_pattern.search(str(header)):
                numbers = [
                    str(cell.value).strip()
                    for cell in column[1:]
                    if cell.value and valid_pattern.match(str(cell.value))
                ]
                result[sheet.title] = numbers

    return result
