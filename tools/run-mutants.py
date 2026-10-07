#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Run attack-guest.py against the correct mock gate and six mutants."""
from __future__ import print_function

import argparse
import os
import shutil
import subprocess
import sys
import tempfile
import time
from urllib.request import urlopen


ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
MUTANTS = ["trust_author", "traversal", "invite_file", "no_expiry", "prefix_slug", "no_size_limit"]


def wait_http(url, timeout=8):
    end = time.time() + timeout
    while time.time() < end:
        try:
            urlopen(url, timeout=1).read()
            return True
        except Exception:
            time.sleep(0.15)
    return False


def stop(proc):
    if proc.poll() is not None:
        return
    try:
        proc.terminate()
        proc.wait(timeout=4)
    except Exception:
        try:
            proc.kill()
        except Exception:
            pass


def run_case(py, clip, mutant, api_port, gate_port, keep):
    label = mutant or "correct"
    base_tmp = tempfile.mkdtemp(prefix="ofg-%s-" % label.replace("_", "-"), dir="/tmp/o8")
    data = os.path.join(base_tmp, "data")
    log = os.path.join(base_tmp, "guest.log")
    env = os.environ.copy()
    env["PYTHONUNBUFFERED"] = "1"
    if mutant:
        env["OFG_MUTANT"] = mutant
    api_cmd = [py, os.path.join(ROOT, "tools/mock/mock_api.py"), "--puerto", str(api_port), "--data", data]
    gate_cmd = [py, os.path.join(ROOT, "tools/mock/mock_gate.py"), "--puerto", str(gate_port),
                "--api", "http://127.0.0.1:%d" % api_port, "--data", data, "--log", log]
    api = subprocess.Popen(api_cmd, cwd=ROOT, env=env, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
    gate = None
    try:
        if not wait_http("http://127.0.0.1:%d/api/ping" % api_port):
            out = api.stdout.read() if api.stdout else ""
            return False, "api did not start\n" + out
        gate = subprocess.Popen(gate_cmd, cwd=ROOT, env=env, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
        time.sleep(0.4)
        attack_cmd = [py, os.path.join(ROOT, "tools/attack-guest.py"),
                      "--api", "http://127.0.0.1:%d" % api_port,
                      "--gate", "http://127.0.0.1:%d" % gate_port,
                      "--clip", clip,
                      "--data", data,
                      "--log", log]
        run = subprocess.run(attack_cmd, cwd=ROOT, env=env, stdout=subprocess.PIPE,
                             stderr=subprocess.STDOUT, text=True, timeout=120)
        expected_pass = mutant is None
        ok = (run.returncode == 0) if expected_pass else (run.returncode != 0)
        status = "PASS" if ok else "FAIL"
        killed = " (killed)" if mutant and run.returncode != 0 else ""
        print("%s %-14s exit=%s%s" % (status, label, run.returncode, killed))
        if not ok or os.environ.get("RUN_MUTANTS_VERBOSE"):
            print(run.stdout)
        return ok, run.stdout
    except subprocess.TimeoutExpired as exc:
        print("FAIL %-14s timeout" % label)
        return False, str(exc)
    finally:
        if gate is not None:
            stop(gate)
        stop(api)
        if keep:
            print("kept %s" % base_tmp)
        else:
            shutil.rmtree(base_tmp, ignore_errors=True)


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument("--clip", default=os.path.join(ROOT, "clip.mp4"))
    parser.add_argument("--api-port", type=int, default=9397)
    parser.add_argument("--gate-port", type=int, default=9398)
    parser.add_argument("--python", default=sys.executable)
    parser.add_argument("--keep", action="store_true")
    args = parser.parse_args(argv)
    cases = [None] + MUTANTS
    ok_all = True
    for case in cases:
        ok, _ = run_case(args.python, os.path.abspath(args.clip), case, args.api_port, args.gate_port, args.keep)
        ok_all = ok_all and ok
    killed = len(MUTANTS) if ok_all else "?"
    print("mutation score: %s/%d" % (killed, len(MUTANTS)))
    return 0 if ok_all else 1


if __name__ == "__main__":
    sys.exit(main())
