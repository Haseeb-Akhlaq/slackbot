import json
import os
from openai import OpenAI
import requests
from dotenv import load_dotenv
from prompts import assistant_instructions
import os

load_dotenv()

client = OpenAI()

GOOGLE_SHEET_URL = os.environ.get("GOOGLE_SHEET_URL")
GOOGLE_SHEET_WEBHOOK_URL = os.environ.get("GOOGLE_SHEET_WEBHOOK_URL")


def save_booking_details(
    event_name, event_time, event_coordinator, event_location, booked_by
):
    webhook_url = GOOGLE_SHEET_WEBHOOK_URL

    data = {
        "event_name": event_name,
        "event_time": event_time,
        "event_coordinator": event_coordinator,
        "event_location": event_location,
        "booked_by": booked_by,
    }

    response = requests.post(webhook_url, json=data)

    print(response.text)

    print("Response from Zapier", response)

    if response.status_code == 200:
        return "event booking was success"
    else:
        print("Error:", response.status_code, response.text)
        return ("Error:", response.status_code, response.text)


def get_all_booked_events():
    url = GOOGLE_SHEET_URL

    response = requests.get(url)

    if response.status_code == 200:
        records = response.json()

        if records:
            return records
        else:
            return "No events are booked yet."

    else:
        print(f"Failed to retrieve records: {response.text}")


def get_details_of_single_event(event_name):
    url = f"{GOOGLE_SHEET_URL}?name={event_name}"

    response = requests.get(url)

    if response.status_code == 200:
        records = response.json()

        if records:
            return records
        else:
            return "No records found with the specified event name."

    else:
        return f"Failed to retrieve records: {response.text}"


def create_assistant():
    assistant = client.beta.assistants.create(
        instructions=assistant_instructions,
        name="SlackChatbot",
        model="gpt-4-1106-preview",
        tools=[
            {
                "type": "function",
                "function": {
                    "name": "book_event",
                    "description": "Book the event",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "event_name": {
                                "type": "string",
                                "description": "Event Name",
                            },
                            "event_time": {
                                "type": "string",
                                "description": "Event time must be in ISO format",
                            },
                            "coordinator": {
                                "type": "string",
                                "description": "The name of the coordinator managing the event",
                            },
                            "event_location": {
                                "type": "string",
                                "description": "The location or venue of the event",
                            },
                        },
                        "required": [
                            "event_name",
                            "event_time",
                            "coordinator",
                            "event_location",
                        ],
                    },
                },
            },
            {
                "type": "function",
                "function": {
                    "name": "get_all_booked_events",
                    "description": "Get all the Scheduled events from the Airtable",
                    "parameters": {"type": "object", "properties": {}, "required": []},
                },
            },
            {
                "type": "function",
                "function": {
                    "name": "get_single_booked_event",
                    "description": "Get the details of the event booked",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "event_name": {
                                "type": "string",
                                "description": "The name of the event of which details to be found",
                            }
                        },
                        "required": ["event_name"],
                    },
                },
            },
        ],
    )
    print(assistant)
