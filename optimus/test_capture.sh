#!/bin/bash
# Capture a small test run and dump output to test_output.log
python precise_fiber_hunter.py --dry --limit 150 2>&1 | tee test_output.log
echo "---END OF TEST---" >> test_output.log
