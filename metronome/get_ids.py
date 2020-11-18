#!/usr/bin/env python3

import json
import sys

# this prints out the job ids when passed the output of `dcos job list --json`. this way we don't need something like jq installed.
if __name__ == "__main__":
    for job in json.load(sys.stdin):
        print(job.get("id"))
