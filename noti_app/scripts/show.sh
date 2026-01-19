#!/bin/bash

# Script to show the notification app window
# Send a message to trigger the app to show itself

echo "Sending show trigger to notification app..."

# Send a special message that will popup the window
curl -d "show:window - trigger" https://ntfy.sh/tom_noti_app_abc123xyz

echo "Window should now be visible"