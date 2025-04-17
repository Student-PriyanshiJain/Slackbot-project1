import json
import tempfile
from urllib.parse import parse_qs
from django import shortcuts
from django.shortcuts import render
import os
from pyngrok import ngrok
from slack_sdk import WebClient
from slack_bolt import App
from dotenv import load_dotenv
import requests
from django.http import JsonResponse , HttpResponse
from django.views.decorators.csrf import csrf_exempt
from slack_bolt.adapter.django import SlackRequestHandler


load_dotenv()

bot_client = WebClient(token=os.environ['SLACK_TOKEN'])

# listener = ngrok.connect(
#     addr="localhost:3001",
#     authtoken=os.getenv('NGROKAUTHTOKEN'),
#     domain=os.getenv('DOMAIN')
# )

# listener = ngrok.connect(3001)
# print("Ngrok URL:", listener.public_url)


app = App(
    token=os.environ.get("SLACK_TOKEN"),
    signing_secret=os.environ.get("SIGNING_SECRET")
)

handler = SlackRequestHandler(app)

@csrf_exempt
def slack_events(request):
    if request.method == 'POST':
        print("Slack event received!")

        try:
           body_str = request.body.decode('utf-8')
           print(" Raw body:", body_str)  

           if request.content_type == "application/json":
            payload = json.loads(body_str)
           elif request.content_type == "application/x-www-form-urlencoded":
                data = parse_qs(body_str)
                payload = json.loads(data["payload"][0])
           else:
                return JsonResponse({"error": "Unsupported content type"}, status=400)
           print("Payload:", payload)
        
           if payload.get('type') == 'url_verification':
            return JsonResponse({'challenge': payload['challenge']})


        # return JsonResponse({'status': 'ok'})
           return handler.handle(request)
        except Exception as e:
            print(" Error decoding JSON:", e)
            return JsonResponse({"error": "invalid json"}, status=400)



    return HttpResponse("Only POST requests allowed", status=405)
@app.event("app_mention")
def handle_app_mention(event, client, logger):
    print(" app_mention event triggered!")
    print("Event payload:", event)

    user_id = event["user"]
    channel_id = event["channel"]
    message_ts = event["ts"]

    client.chat_postMessage(
        channel=channel_id,
        thread_ts=message_ts,
        text=f"Hi <@{user_id}>! Please click the button below to upload your Google Sheet.",
        blocks=[
                {
                    "type": "actions",
                    "block_id": "upload_sheet_block",
                    "elements": [
                        {
                            "type": "button",
                            "text": {"type": "plain_text", "text": "Upload Sheet "},
                            "action_id": "open_modal"
                        }
                    ]
                }
               ]
        )
    print(" Mention received") 
@app.action("open_modal")
def open_modal(ack, body, client, logger):
    ack()
    trigger_id = body["trigger_id"]

    modal_view = {
        "type": "modal",
        "callback_id": "get_sheet_form",
        "title": {"type": "plain_text", "text": "Google Sheet to CSV"},
        "submit": {"type": "plain_text", "text": "Get CSV"},
        "close": {"type": "plain_text", "text": "Cancel"},
        "blocks": [
            {
                "type": "input",
                "block_id": "sheet_url_block",
                "element": {
                    "type": "plain_text_input",
                    "action_id": "sheet_url_input",
                    "placeholder": {
                        "type": "plain_text",
                        "text": "Paste Google Sheet URL or ID"
                    }
                },
                "label": {"type": "plain_text", "text": "Google Sheet Link or ID"}
            }
        ]
    }

    try:
        client.views_open(trigger_id=trigger_id, view=modal_view)
    except Exception as e:
        logger.error(f"Error opening modal: {e}")
        
@app.view("get_sheet_form")
def handle_view_submission(ack, body, client, logger):
    ack()
    user = body["user"]["id"]
    sheet_url = body["view"]["state"]["values"]["sheet_url_block"]["sheet_url_input"]["value"]
    channel_id = body["view"]["private_metadata"]
    try:
        sheet_id = extract_sheet_id(sheet_url)
        csv_data = fetch_google_sheet_as_csv(sheet_id)

        with tempfile.NamedTemporaryFile(delete=False, suffix=".csv") as tmp_file:
            tmp_file.write(csv_data.encode("utf-8"))
            tmp_file_path = tmp_file.name

        # with open(tmp_file_path, "rb") as f:
        client.files_upload_v2(
            channel=os.environ.get("CHANNEL_ID"),
            file=tmp_file_path,
            # filetype="csv",
            filename="google_sheet.csv",
            title="Here's your CSV file from Google Sheet"
        )
    except Exception as e:
        logger.error(f"Sheet processing error: {e}")
        client.chat_postMessage(channel=user, text=f"Failed to fetch sheet: {e}")

# def slack_events(request):
#     if request.method == "POST":
#         return JsonResponse({"status": "received"})
#     return JsonResponse({"status": "ready"})

def extract_sheet_id(sheet_input):
    if "docs.google.com" in sheet_input:
        return sheet_input.split("/d/")[1].split("/")[0]
    return sheet_input.strip()

def fetch_google_sheet_as_csv(sheet_id):
    url = f"https://docs.google.com/spreadsheets/d/{sheet_id}/export?format=csv"
    response = requests.get(url)
    if response.status_code != 200:
        raise Exception("Make sure the sheet is shared publicly or with 'Anyone with the link'.")
    return response.text

if __name__ == "__main__" :
    app.start(port=int(os.environ.get("PORT",3000)))