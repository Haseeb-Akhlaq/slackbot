import os
import json
from slack_bolt import App
from slack_bolt.adapter.flask import SlackRequestHandler
from slack_sdk.signature import SignatureVerifier
from flask import Flask, request, abort
from openai import OpenAI
from dotenv import load_dotenv
from functools import wraps
import time
import shelve

import functions

load_dotenv()

SLACK_BOT_TOKEN = os.environ.get("SLACK_BOT_TOKEN")
SLACK_SIGNING_SECRET = os.environ.get("SLACK_SIGNING_SECRET")

app = App(
    token=SLACK_BOT_TOKEN,
    signing_secret=SLACK_SIGNING_SECRET,
)

flask_app = Flask(__name__)
handler = SlackRequestHandler(app)

client = OpenAI()


# --------------------------------------------------------------
# Thread management
# --------------------------------------------------------------
def check_if_thread_exists(slack_thread_id):
    with shelve.open("threads_db") as threads_shelf:
        return threads_shelf.get(slack_thread_id, None)


def store_thread(openai_thread_Id, slack_thread_id):
    with shelve.open("threads_db", writeback=True) as threads_shelf:
        threads_shelf[slack_thread_id] = openai_thread_Id


# --------------------------------------------------------------
# Function to trigger on message mention on Slack
# --------------------------------------------------------------


@app.event("app_mention")
def mention_handler(event, say):
    thread_ts = event.get("thread_ts", event["ts"])
    channel_id = event["channel"]
    user_id = event["user"]

    user_info = app.client.users_info(user=user_id)
    user_name = user_info["user"]["real_name"] if user_info["ok"] else "Unknown User"

    openai_thread_Id = check_if_thread_exists(thread_ts)

    # If a thread doesn't exist, create one and store it
    if openai_thread_Id is None:
        print(f"Creating new thread for with slack thread ID {thread_ts}")
        thread = client.beta.threads.create()
        store_thread(thread.id, thread_ts)
        openai_thread_Id = thread.id

    message = client.beta.threads.messages.create(
        thread_id=openai_thread_Id, role="user", content=f"{event['text']}"
    )

    run = client.beta.threads.runs.create(
        assistant_id=os.environ.get("ASSISTANT_ID"),
        thread_id=openai_thread_Id,
    )

    while True:
        run_status = client.beta.threads.runs.retrieve(
            thread_id=openai_thread_Id,
            run_id=run.id,
        )

        if run_status.status == "completed":
            break

        elif run_status.status == "requires_action":
            for tool_call in run_status.required_action.submit_tool_outputs.tool_calls:
                if tool_call.function.name == "book_event":
                    arguments = json.loads(tool_call.function.arguments)

                    output = functions.save_booking_details(
                        arguments["event_name"],
                        arguments["event_time"],
                        arguments["coordinator"],
                        arguments["event_location"],
                        user_name,
                    )

                    client.beta.threads.runs.submit_tool_outputs(
                        thread_id=openai_thread_Id,
                        run_id=run.id,
                        tool_outputs=[
                            {
                                "tool_call_id": tool_call.id,
                                "output": json.dumps(output),
                            }
                        ],
                    )
                elif tool_call.function.name == "get_all_booked_events":
                    app.client.chat_postMessage(
                        channel=channel_id,
                        text="fetching booked events...",
                        thread_ts=thread_ts,
                    )

                    arguments = json.loads(tool_call.function.arguments)

                    output = functions.get_all_booked_events()

                    client.beta.threads.runs.submit_tool_outputs(
                        thread_id=openai_thread_Id,
                        run_id=run.id,
                        tool_outputs=[
                            {
                                "tool_call_id": tool_call.id,
                                "output": json.dumps(output),
                            }
                        ],
                    )
                elif tool_call.function.name == "get_single_booked_event":
                    app.client.chat_postMessage(
                        channel=channel_id,
                        text="fetching event details...",
                        thread_ts=thread_ts,
                    )

                    arguments = json.loads(tool_call.function.arguments)

                    output = functions.get_details_of_single_event(
                        arguments["event_name"]
                    )

                    client.beta.threads.runs.submit_tool_outputs(
                        thread_id=openai_thread_Id,
                        run_id=run.id,
                        tool_outputs=[
                            {
                                "tool_call_id": tool_call.id,
                                "output": json.dumps(output),
                            }
                        ],
                    )

            time.sleep(1)

    messages = client.beta.threads.messages.list(thread_id=openai_thread_Id)

    app.client.chat_postMessage(
        channel=channel_id,
        text=messages.data[0].content[0].text.value,
        thread_ts=thread_ts,
    )


signature_verifier = SignatureVerifier(SLACK_SIGNING_SECRET)


def require_slack_verification(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not verify_slack_request():
            abort(403)
        return f(*args, **kwargs)

    return decorated_function


def verify_slack_request():
    # Get the request headers
    timestamp = request.headers.get("X-Slack-Request-Timestamp", "")
    signature = request.headers.get("X-Slack-Signature", "")

    # Check if the timestamp is within five minutes of the current time
    current_timestamp = int(time.time())
    if abs(current_timestamp - int(timestamp)) > 60 * 5:
        return False

    # Verify the request signature
    return signature_verifier.is_valid(
        body=request.get_data().decode("utf-8"),
        timestamp=timestamp,
        signature=signature,
    )


@flask_app.route("/slack/events", methods=["POST"])
@require_slack_verification
def slack_events():
    """
    Route for handling Slack events.
    This function passes the incoming HTTP request to the SlackRequestHandler for processing.

    Returns:
        Response: The result of handling the request.
    """

    print("request came here")

    return handler.handle(request)


if __name__ == "__main__":
    flask_app.run(host="0.0.0.0", port=8000)
