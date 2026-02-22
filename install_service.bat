@echo off
REM Telegram-Ollama Bot Service Installation
REM Run this as Administrator

echo Installing Telegram-Ollama Bot as Windows Service...

REM Install the service
C:\nssm\nssm-2.24\win64\nssm.exe install TelegramOllamaBot "E:\telegram-ollama-bot\venv\Scripts\python.exe"

REM Set the arguments
C:\nssm\nssm-2.24\win64\nssm.exe set TelegramOllamaBot AppParameters "E:\telegram-ollama-bot\bot.py"

REM Set the working directory
C:\nssm\nssm-2.24\win64\nssm.exe set TelegramOllamaBot AppDirectory "E:\telegram-ollama-bot"

REM Set description
C:\nssm\nssm-2.24\win64\nssm.exe set TelegramOllamaBot Description "Telegram bot connected to local Ollama LLM"

REM Set display name
C:\nssm\nssm-2.24\win64\nssm.exe set TelegramOllamaBot DisplayName "Telegram-Ollama Bot"

REM Set to auto-start
C:\nssm\nssm-2.24\win64\nssm.exe set TelegramOllamaBot Start SERVICE_AUTO_START

REM Set restart on failure
C:\nssm\nssm-2.24\win64\nssm.exe set TelegramOllamaBot AppExit Default Restart

REM Set stdout log
C:\nssm\nssm-2.24\win64\nssm.exe set TelegramOllamaBot AppStdout "E:\telegram-ollama-bot\logs\bot.log"

REM Set stderr log
C:\nssm\nssm-2.24\win64\nssm.exe set TelegramOllamaBot AppStderr "E:\telegram-ollama-bot\logs\bot.log"

REM Enable log rotation
C:\nssm\nssm-2.24\win64\nssm.exe set TelegramOllamaBot AppRotateFiles 1
C:\nssm\nssm-2.24\win64\nssm.exe set TelegramOllamaBot AppRotateBytes 10485760
C:\nssm\nssm-2.24\win64\nssm.exe set TelegramOllamaBot AppRotateOnline 1

REM Create logs directory
if not exist "E:\telegram-ollama-bot\logs" mkdir "E:\telegram-ollama-bot\logs"

REM Set service dependencies (Wonder Engine must be running)
C:\nssm\nssm-2.24\win64\nssm.exe set TelegramOllamaBot DependOnService WonderEngine

REM Start the service
C:\nssm\nssm-2.24\win64\nssm.exe start TelegramOllamaBot

echo.
echo Service installed and started!
echo Check status with: sc query TelegramOllamaBot
echo View logs at: E:\telegram-ollama-bot\logs\bot.log
pause
