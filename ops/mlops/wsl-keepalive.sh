#!/usr/bin/env sh
# Flag exclusiva desta tarefa; removida por stack.ps1 -Encerrar.
remaining=2400
while [ -f "$1" ] && [ "$remaining" -gt 0 ]; do
    sleep 3
    remaining=$((remaining - 1))
done
