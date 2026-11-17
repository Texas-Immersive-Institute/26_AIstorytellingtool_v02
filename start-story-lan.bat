@echo off
rem Starts Story so phones and laptops on your network can open the audience chat.
rem Windows Firewall may ask the first time; allow it on private networks only.
call "%~dp0start-story.bat" --lan %*
