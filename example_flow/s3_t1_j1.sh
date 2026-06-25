#!/bin/csh
# Stage 3 / Task 1 / Job 1 — merge branch outputs into final_output.txt

foreach f (output_1.txt output_2.txt)
  if ( ! -f $f ) then
    echo "ERROR: missing input $f" >&2
    exit 1
  endif
end

echo "# WinFlow example — merged results" > final_output.txt
echo "# merged at `date`" >> final_output.txt
echo "" >> final_output.txt

foreach f (output_1.txt output_2.txt)
  echo "===== $f =====" >> final_output.txt
  cat $f >> final_output.txt
  echo "" >> final_output.txt
end
