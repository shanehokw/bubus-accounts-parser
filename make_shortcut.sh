#!/bin/zsh
# Builds two double-clickable apps in the "Shortcuts" folder (drag them to the Desktop or Dock):
#   "Statements to Excel.app"       starts the app in the background (if not running) and opens it
#   "Stop Statements to Excel.app"  stops it
# Run again if this folder moves.
set -e
cd "$(dirname "$0")"
DIR="$PWD"
URL="http://127.0.0.1:8501"
LOG="$HOME/Library/Logs/statements-to-excel.log"
OUT="$DIR/Shortcuts"
mkdir -p "$OUT"

osacompile -o "$OUT/Statements to Excel.app" -e "
set appDir to \"$DIR\"
try
	do shell script \"curl -sf -o /dev/null $URL\"
on error
	-- Only the server goes to the background (with all output redirected), so this returns at once.
	do shell script \"cd \" & quoted form of appDir & \"; STREAMLIT_SERVER_HEADLESS=true nohup .venv/bin/streamlit run app.py > '$LOG' 2>&1 < /dev/null &\"
	repeat 30 times
		delay 0.5
		try
			do shell script \"curl -sf -o /dev/null $URL\"
			exit repeat
		end try
	end repeat
end try
open location \"$URL\"
"

osacompile -o "$OUT/Stop Statements to Excel.app" -e "
try
	do shell script \"pkill -f 'streamlit run app.py'\"
end try
display notification \"Statements to Excel has stopped.\" with title \"Statements to Excel\"
"

echo "Created in $OUT: Statements to Excel.app, Stop Statements to Excel.app"
[ -n "$NO_OPEN" ] || open "$OUT"
