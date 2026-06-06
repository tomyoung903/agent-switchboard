#!/bin/bash

# Script to show the notification app window
# Send a message to trigger the app to show itself

echo "Sending show trigger to notification app..."

# Send a special message that will popup the window
NTFY_SERVER="${NTFY_SERVER:-https://ntfy.sh}"
NTFY_TOPIC="${NTFY_TOPIC:-agent_switchboard_demo_topic_change_me}"

curl -d "show:window - trigger" "${NTFY_SERVER%/}/$NTFY_TOPIC"

echo "Window should now be visible"
