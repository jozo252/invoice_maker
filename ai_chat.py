import os
from dotenv import load_dotenv
from openai import OpenAI
from functools import wraps
from datetime import datetime, timezone
from difflib import get_close_matches
import json
import re
import ast
load_dotenv()  
openai_key = os.getenv("OPENAI_API_KEY")
client = OpenAI(api_key=openai_key)




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
        response = client.chat.completions.create(
            model="gpt-4.1",
            messages=[
                {"role": "system", "content": "You are an invoice data extractor. Return ONLY a valid Python dictionary with the required fields."},
                {"role": "user", "content": f"""
                Extract invoice data from this text and return ONLY a Python dictionary:
                {data}
                
                Required dictionary keys:
                - client_name (string)
                - date (string in YYYY-MM-DD format)
                - due_date (string in YYYY-MM-DD format)
                - description (string)
                - quantity (number)
                - unit (string)
                - price_per_item (number)
                - total_cost (quantity * price_per_item)
                - currency (3-letter code)
                
                Example output format:
                {{
                    "client_name": "Example Client",
                    "date": "2023-12-01",
                    "due_date": "2023-12-31",
                    "description": "Sample Service",
                    "quantity": 2,
                    "unit": "hours",
                    "price_per_item": 50,
                    "total_cost": 100,
                    "currency": "EUR"
                }}
                """}
            ]
        )
        
        # Get the raw response
        response_str = response.choices[0].message.content
        
        # Clean the response - remove markdown code blocks if present
        cleaned_str = re.sub(r'```python|```', '', response_str).strip()
        
        # First try json.loads in case it's JSON-like
        try:
            json_str = cleaned_str.replace("'", '"')
            return json.loads(json_str)
        except json.JSONDecodeError:
            pass
        
        # Then try ast.literal_eval for Python dict string
        try:
            return ast.literal_eval(cleaned_str)
        except (ValueError, SyntaxError) as e:
            print(f"Could not parse response: {e}\nResponse was: {cleaned_str}")
            return None
            
    except Exception as e:
        print(f"Error generating invoice: {str(e)}")
        return None






#invoice_maker("vytvor fakturu pre klienta gf elektro, datum vystavenia 2023-12-01, splatnost 2023-12-31, popis sluzby, mnozstvo 2, jednotka hodiny, cena za kus 50, mena EUR")



