@echo off
cd C:\Users\alawl\Desktop\Game Dev Projects\AI Game\ai-game
title AI cooking game server
set PYTHONIOENCODING=utf-8
python server.py > log.txt 2>&1
