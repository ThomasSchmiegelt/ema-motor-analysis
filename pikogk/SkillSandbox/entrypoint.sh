#!/usr/bin/env bash
#
# Runs inside the sandbox container. /work is a bind-mounted scratch
# directory (per invocation) containing Skill.csproj + Generator.cs +
# params.json, written by the host. Never trust anything in /work beyond
# reading it - this script's job is just: compile, run under Xvfb, report.
#
set -uo pipefail

cd /work || exit 20

echo "=== compiling ==="
dotnet build Skill.csproj -c Release -o /work/bin > /work/compile_output.txt 2>&1
COMPILE_EXIT=$?

if [ $COMPILE_EXIT -ne 0 ]; then
  echo '{"stage":"compile","ok":false}'
  cat /work/compile_output.txt
  exit 10
fi

echo "=== starting virtual display (Xvfb + software GL) ==="
Xvfb :77 -screen 0 800x600x24 > /work/xvfb.log 2>&1 &
XVFB_PID=$!
sleep 1

export DISPLAY=:77
export LIBGL_ALWAYS_SOFTWARE=1

echo "=== running harness ==="
dotnet /opt/harness/Harness.dll /work/bin/Skill.dll /work/params.json /work/result.stl
HARNESS_EXIT=$?

kill "$XVFB_PID" 2>/dev/null || true

exit $HARNESS_EXIT
