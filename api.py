import json
import os
import re
import subprocess
import tempfile

import dotenv
import openpyxl
import requests

dotenv.load_dotenv()
WHATSAPP_ACCESS_TOKEN = os.getenv("WHATSAPP_ACCESS_TOKEN")
WHATSAPP_PHONE_NUMBER_ID = os.getenv("WHATSAPP_PHONE_NUMBER_ID")
WHATSAPP_BUSINESS_ACCOUNT_ID = os.getenv("WHATSAPP_BUSINESS_ACCOUNT_ID")
WHATSAPP_APP_ID = os.getenv("WHATSAPP_APP_ID")


def generate_components(texts_list):
    """Generates the components for the WhatsApp message."""
    # If all the texts in Variables are empty, return an empty list
    if all(element == "" for element in texts_list):
        return []

    parameters = []
    for text in texts_list:
        component = {"type": "text", "text": text}
        parameters.append(component)

    output = [{"type": "body", "parameters": parameters}]
    return output


def send_whatsapp_message(
    template_name,
    language,
    country_code,
    phone_number,
    components,
):

    if language == "English":
        code = "en_US"
    elif language == "Hindi":
        code = "hi"

    url = f"https://graph.facebook.com/v17.0/{WHATSAPP_PHONE_NUMBER_ID}/messages"
    headers = {
        "Authorization": f"Bearer {WHATSAPP_ACCESS_TOKEN}",
        "Content-Type": "application/json",
    }

    data = {
        "messaging_product": "whatsapp",
        "to": str(country_code) + str(phone_number),
        "type": "template",
        "template": {
            "name": template_name,
            "language": {"code": code},
            "components": components,
        },
    }

    response = requests.post(url, headers=headers, json=data)

    output = {"status_code": response.status_code, "response": response.text}
    return output


def get_message_templates():

    url = f"https://graph.facebook.com/v17.0/{WHATSAPP_BUSINESS_ACCOUNT_ID}/message_templates"
    headers = {"Authorization": f"Bearer {WHATSAPP_ACCESS_TOKEN}"}
    response = requests.get(url, headers=headers)
    response_data = response.json()
    names = [item["name"] for item in response_data.get("data", [])]

    return names


def upload_media(file_bytes, file_type):
    """
    Uploads a media file to WhatsApp Business API.
    Parameters:
        file_bytes (bytes): The bytes of the file to upload.
        file_type (str): The MIME type of the file.

    Returns:
        str: The ID of the uploaded file.

    Docs: https://developers.facebook.com/docs/whatsapp/cloud-api/reference/media
    """

    # Determine the file extension from the file_type
    if file_type == "image/jpeg" or file_type == "image/jpg":
        file_extension = ".jpeg"
    elif file_type == "image/png":
        file_extension = ".png"
    else:
        raise ValueError("Unsupported file_type")

    # Create a temporary file with the file_bytes
    with tempfile.NamedTemporaryFile(suffix=file_extension, delete=False) as temp_file:
        temp_file.write(file_bytes)
        file_path = temp_file.name

    # Construct the command
    command = [
        "curl",
        "-X",
        "POST",
        f"https://graph.facebook.com/v18.0/{WHATSAPP_PHONE_NUMBER_ID}/media",
        "-H",
        f"Authorization: Bearer {WHATSAPP_ACCESS_TOKEN}",
        "-F",
        f'file=@"{file_path}"',
        "-F",
        f'type="{file_type}"',
        "-F",
        'messaging_product="whatsapp"',
    ]

    try:
        # Run the command and capture the output
        completed_process = subprocess.run(command, stdout=subprocess.PIPE, text=True)
    finally:
        # Ensure the temporary file is deleted after the work is done
        os.remove(file_path)

    return completed_process.stdout


def excel_to_phone_list(file):
    """
    Extracts the mobile numbers from all the sheets in an Excel file.
    Output: {sheet1_name: [mobile_numbers], sheet2_name: [mobile_numbers]}
    """
    result = {}

    mobile_number_pattern = re.compile(r"(mobile|phone|cell|tel|contact)", re.I)
    valid_number_pattern = re.compile(r"\d{10}")

    wb = openpyxl.load_workbook(file)
    for sheet in wb.worksheets:
        for column in sheet.iter_cols():
            # Check if the column name contains a mobile number keyword
            if mobile_number_pattern.search(column[0].value):
                # Extract the mobile numbers from the column
                mobile_numbers = [
                    cell.value
                    for cell in column[1:]
                    if valid_number_pattern.search(str(cell.value))
                ]
                result[sheet.title] = mobile_numbers

    return result
