#!/bin/csh
# Stage 1 / Task 1 / Job 1 — validate input and produce temp.txt

if ( ! -f example_flow/input.txt ) then
  echo "ERROR: missing example_flow/input.txt" >&2
  exit 1
endif

set nlines = `wc -l < example_flow/input.txt`
if ( $nlines < 1 ) then
  echo "ERROR: example_flow/input.txt is empty" >&2
  exit 1
endif

echo "# validated input" > temp.txt
cat example_flow/input.txt >> temp.txt
echo "# validated at `date`" >> temp.txt
