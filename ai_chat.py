import os
from dotenv import load_dotenv
from openai import OpenAI
from functools import wraps
from datetime import datetime, timezone
from difflib import get_close_matches
import json
import re
import ast
from flask import current_app





"""""
def with_app_context(func):
    @wraps(func)
    def wrapper(*args, **kwargs):
        with app.app_context():
            return func(*args, **kwargs)
    return wrapper
"""



def invoice_maker(data):
    try:
        openai_key = current_app.config("OPENAI_API_KEY")
        client = OpenAI(api_key=openai_key)

        response = client.chat.completions.create(
            model="gpt-4.1",
            messages=[
                {
                    "role": "system",
                    "content": (
                        "You are an invoice data extractor. Return ONLY a valid Python dictionary "
                        "with the required fields and nothing else."
                    )
                },
                {
                    "role": "user",
                    "content": f"""
            Extract invoice data from this text and return ONLY a Python dictionary:

            {data}

            Required structure:
            {{
                "client_name": "Client Name",
                "date": "YYYY-MM-DD",
                "due_date": "YYYY-MM-DD",
                "currency": "EUR",
                "items": [
                    {{
                        "description": "Service or Product",
                        "quantity": 2,
                        "unit": "ks",
                        "price_per_item": 50.0
                    }},
                    ...
                ]
            }}

            Each item should be a dictionary with:
            - description (string)
            - quantity (number)
            - unit (string)
            - price_per_item (number)

            Do not include markdown or any explanation. Return only the Python dictionary.
            """
                }
            ]
        )

        response_str = response.choices[0].message.content.strip()
        cleaned_str = re.sub(r'```(python)?|```', '', response_str).strip()

        # Try JSON-style first
        try:
            json_str = cleaned_str.replace("'", '"')
            return json.loads(json_str)
        except json.JSONDecodeError:
            pass

        # Try Python dict parsing
        try:
            return ast.literal_eval(cleaned_str)
        except (ValueError, SyntaxError) as e:
            print(f"Could not parse response: {e}\nResponse was: {cleaned_str}")
            return None

    except Exception as e:
        print(f"Error generating invoice: {str(e)}")
        return None






#invoice_maker("vytvor fakturu pre klienta gf elektro, datum vystavenia 2023-12-01, splatnost 2023-12-31, popis sluzby, mnozstvo 2, jednotka hodiny, cena za kus 50, mena EUR")



