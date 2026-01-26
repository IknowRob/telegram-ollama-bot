@echo off
REM Telegram-Ollama Bot - Manual Start
REM Location: E:\telegram-ollama-bot\start_bot.bat

cd /d E:\telegram-ollama-bot
call venv\Scripts\activate.bat
python bot.py
pause
