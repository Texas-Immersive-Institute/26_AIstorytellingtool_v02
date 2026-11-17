#!/bin/bash
# Starts Story so phones and laptops on your network can open the audience chat.
# macOS may ask to allow incoming connections the first time; allow it.
exec "$(dirname "$0")/start-story.command" --lan "$@"
