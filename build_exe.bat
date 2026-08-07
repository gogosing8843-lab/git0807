@echo off
chcp 65001 > nul
echo [상수도 관리 시스템 EXE 독립 실행 파일 빌드 중...]
pyinstaller --noconsole --onefile --clean --name="상수도_관리_시스템" app.py
echo [빌드 완료!]
