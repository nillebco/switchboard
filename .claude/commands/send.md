---
description: Send a message to a contact or group via Signal, Telegram, or WhatsApp using the switchboard API running locally at http://localhost:8018.
---

Send a message using the switchboard messaging API.

## API details

- Base URL: `http://localhost:8018/api/v1`
- Auth header: `X-API-Key: <your API_KEY from .env>`

## Endpoints

**Send to a specific recipient:**
```
POST /send?transport=<signal|telegram|whatsapp>
{"recipient": "<value>", "message": "<text>"}
```

**Notify the owner (no recipient needed):**
```
POST /notify?transport=<signal|telegram|whatsapp>
{"message": "<text>"}
```

**List groups:**
```
GET /send/groups?transport=<signal|whatsapp>
```

## Recipient formats
- Signal: phone number (`+33612345678`) or group ID (`group.XXX…=`)
- Telegram: chat ID (integer, negative for groups)
- WhatsApp: phone number or JID (`120363…@g.us` for groups)

## Instructions

$ARGUMENTS

Parse the user's intent from the arguments above:
1. If no transport is specified, default to **telegram**.
2. If the user wants to notify themselves (no specific recipient), use `POST /notify` instead of `POST /send`.
3. If the user asks to list groups, call `GET /send/groups`.
4. If you don't know the API key, read it from the `.env` file in this repository.

Use the Bash tool to make the API call with `curl`. Show the response.
