import os, runpy
os.environ["DEC_HOUR"] = "9"
runpy.run_path("research/gas_test.py", run_name="__main__")
