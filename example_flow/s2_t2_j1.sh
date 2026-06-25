#!/bin/csh
# Stage 2 / Task 2 / Job 1 — parallel branch (runs alongside task_1)

sleep 5
echo "Stage:2 / Task:2 / Job:1" > output_2.txt
echo "# source: temp.txt" >> output_2.txt
tail -n +1 temp.txt >> output_2.txt
