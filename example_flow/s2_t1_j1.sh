#!/bin/csh
# Stage 2 / Task 1 / Job 1 — first half of branch-1 processing

sleep 5
echo "Stage:2 / Task:1 / Job:1" > output_1.txt
echo "# source: temp.txt" >> output_1.txt
tail -n +1 temp.txt >> output_1.txt
