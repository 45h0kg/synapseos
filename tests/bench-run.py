"""Runs the benchmark inside the VM and prints one BENCH line per result."""
import json
import os
import random
import re
import shutil
import struct
import subprocess
import sys
import time
from importlib.machinery import SourceFileLoader

CORPUS, MODELS, WHEEL = sys.argv[1:4]
SW = "/run/current-system/sw/bin"
wrapper = open(shutil.which("synapse-detonate")).read()
PYTHON, SCRIPT = re.search(r"exec (\S+/python3) (\S+detonate\.py)", wrapper).groups()
detonate = SourceFileLoader("detonate", SCRIPT).load_module()


def emit(kind, **fields):
    print("BENCH " + json.dumps({"kind": kind, **fields}), flush=True)


def run(cmd, timeout=600, env=None, shell=True):
    start = time.time()
    try:
        done = subprocess.run(cmd, shell=shell, capture_output=True, text=True, errors="replace",
                              timeout=timeout, env=env)
        return done.returncode, done.stdout + done.stderr, time.time() - start
    except subprocess.TimeoutExpired as error:
        out = (error.stdout or b"").decode("utf-8", "replace") if isinstance(error.stdout, bytes) else (error.stdout or "")
        return 124, out, time.time() - start


def step(name, cmd, timeout=600, tail=900):
    rc, out, secs = run(cmd, timeout)
    emit("step", name=name, rc=rc, secs=round(secs, 1), out=out[-tail:])
    return rc, out


def control(entry):
    stem = entry["file"].rsplit(".", 1)[0]
    marker = f"/tmp/fired-{stem}"
    cmd = ("systemd-run --quiet --wait --collect --uid=65534 --setenv=BENCH_CONTROL=1 --setenv=HOME=/var/tmp/ctl "
           f"--setenv=PATH={SW} -p PrivateNetwork=yes -p RuntimeMaxSec=12 -p WorkingDirectory=/tmp -- "
           f"{PYTHON} {SCRIPT} _load {entry['runtime']} {entry['path']}")
    run(cmd, 40)
    return os.path.exists(marker)


def scan(path, runtime, timeout=60):
    rc, out, secs = run(f"synapse-detonate scan {path} --runtime {runtime} --timeout {timeout} --memory 3G 2>&1", timeout * 2 + 120)
    verdict = re.search(r"^verdict: (\S+)", out, re.M)
    digest = re.search(r"^digest:\s+(\S+)", out, re.M)
    receipt = re.search(r"^receipt: (\S+)", out, re.M)
    findings = [l.split(None, 2) for l in out.splitlines() if re.match(r"  (critical|high|medium)\s", l)]
    return dict(rc=rc, verdict=verdict.group(1) if verdict else "crash", digest=digest.group(1) if digest else None,
                secs=round(secs, 1), findings=[" ".join(f[:3]) for f in findings][:14],
                receipt=receipt.group(1) if receipt else None, tail="" if verdict else out[-500:])


def static(path):
    env = dict(os.environ, PYTHONPATH=WHEEL)
    # picklescan's __main__ drops main()'s return value, so the exit code must come from main itself.
    code = "import sys; from picklescan.cli import main; sys.exit(main())"
    rc, out, _ = run([PYTHON, "-c", code, "-p", path], 60, env, shell=False)
    return {0: "clean", 1: "flagged"}.get(rc, f"error-{rc}")


def corpus():
    entries = json.load(open(f"{CORPUS}/manifest.json"))
    for entry in entries:
        entry["path"] = f"{CORPUS}/{entry['file']}"
    real = [("stories260K.gguf", "llama"), ("stories260K.gguf", "jinja"), ("stories15M-q4_0.gguf", "llama"),
            ("stories15M-q4_0.gguf", "jinja"), ("stories15M.pt", "torch")]
    for name, runtime in real:
        entries.append(dict(file=name, path=f"{MODELS}/{name}", runtime=runtime, label="benign", group="real",
                            technique=runtime, must_fire=False))
    os.makedirs("/var/tmp/ctl/.aws", exist_ok=True)
    with open("/var/tmp/ctl/.aws/credentials", "w") as f:
        f.write("[default]\naws_access_key_id = AKIACONTROLCONTROLCO\n")
    os.system("chmod -R a+rX /var/tmp/ctl")
    for entry in entries:
        timeout = 90 if entry["runtime"] == "torch" or entry["group"] == "real" else 30
        fired = control(entry) if entry["group"] in ("shell", "python", "behaviour", "evasion", "torch", "bypass") else None
        result = scan(entry["path"], entry["runtime"], timeout)
        result.update(file=entry["file"], label=entry["label"], group=entry["group"], technique=entry["technique"],
                      runtime=entry["runtime"], fired=fired,
                      static=static(entry["path"]) if entry["runtime"] in ("pickle", "torch") else "n/a")
        emit("sample", **result)


def fuzz():
    base = open(f"{MODELS}/stories260K.gguf", "rb").read()
    head = detonate.parse_gguf(base)[2] + 64
    rng = random.Random(7)
    outcomes = {}
    slowest = 0.0
    for _ in range(20000):
        blob = bytearray(base[:head])
        for _ in range(rng.randint(1, 8)):
            at = rng.randrange(len(blob))
            mode = rng.randint(0, 3)
            if mode == 0:
                blob[at] = rng.randrange(256)
            elif mode == 1 and at + 8 < len(blob):
                blob[at:at + 8] = rng.choice([b"\xff" * 8, b"\0" * 8, struct.pack("<Q", 2 ** 31),
                                              struct.pack("<Q", rng.randrange(2 ** 64))])
            elif mode == 2:
                blob = blob[:at]
            else:
                blob[at] ^= 1 << rng.randrange(8)
            if len(blob) < 26:
                blob = bytearray(base[:64])
        start = time.time()
        try:
            detonate.gguf_twin(bytes(blob))
            name = "ok"
        except (ValueError, IndexError, RecursionError, struct.error) as error:
            name = "rejected:" + type(error).__name__
        except Exception as error:
            name = "UNHANDLED:" + type(error).__name__
        outcomes[name] = outcomes.get(name, 0) + 1
        slowest = max(slowest, time.time() - start)
    emit("fuzz", outcomes=outcomes, slowest=round(slowest, 3))
    with open("/tmp/malformed.gguf", "wb") as f:
        f.write(b"GGUF" + struct.pack("<IQQ", 3, 2 ** 40, 2 ** 40) + b"\0" * 64)
    emit("malformed", **scan("/tmp/malformed.gguf", "jinja"))


def repeatability():
    for file, runtime in [("sh-os-system.pkl", "pickle"), ("act-exfil-http-plain.pkl", "pickle"), ("tpl-cycler.gguf", "jinja")]:
        digests = [scan(f"{CORPUS}/{file}", runtime)["digest"] for _ in range(5)]
        emit("repeat", file=file, runs=5, distinct=len(set(digests)))


def pipelines():
    model = "/etc/synapseos/models/stories260K.gguf"
    step("llama-binaries", f"ls {SW} | grep llama")
    step("llama-sandbox", f'synapse-sandbox --memory 1G -- {SW}/llama-completion -no-cnv -m {model} -p "Once upon a time" -n 64 2>&1', 240, 1400)
    step("llama-direct-speed", f'{SW}/llama-completion -no-cnv -m {model} -p "Once upon a time" -n 256 2>&1 | tail -14', 240, 1400)
    step("torch-load-direct", f'{PYTHON} -c "import torch,time; t=time.time(); torch.load(\'{MODELS}/stories15M.pt\', weights_only=False); print(time.time()-t)"')
    step("garak-blank", "synapse-garak --target_type test.Blank --probes test.Test 2>&1")
    opts = json.dumps({"ggml": {"GgmlGenerator": {"path_to_ggml_main": f"{SW}/llama-completion"}}})
    garak = f"synapse-garak --target_type ggml --target_name {model} --generator_options '{opts}' --generations 1 --probes test.Test 2>&1"
    step("garak-ggml-default-flags", garak, 600, 1400)
    bare = json.dumps({"ggml": {"GgmlGenerator": {"path_to_ggml_main": f"{SW}/llama-completion", "extra_ggml_flags": []}}})
    step("garak-ggml-no-flags", garak.replace(opts, bare), 600, 1400)
    step("garak-ggml-promptinject", garak.replace("test.Test", "promptinject.HijackHateHumans"), 1200, 2500)
    os.makedirs("/tmp/ins", exist_ok=True)
    with open("/tmp/ins/canary.py", "w") as f:
        f.write("from inspect_ai import Task, task\nfrom inspect_ai.dataset import Sample\n"
                "from inspect_ai.scorer import includes\nfrom inspect_ai.solver import generate\n\n\n@task\n"
                "def canary():\n    return Task(dataset=[Sample(input='Say CANARY', target='CANARY')], solver=generate(), scorer=includes())\n")
    step("inspect-mock", "cd /tmp/ins && HOME=/tmp/ins inspect eval canary.py --model mockllm/model --display plain 2>&1")
    step("triage-ai-profile", f"({SW}/timeout -s INT 8 synapse-triage lo ai 2>&1 &) ; sleep 2; "
                              f"{PYTHON} -m http.server 8000 --bind 127.0.0.1 >/dev/null 2>&1 & sleep 1; curl -s -o /dev/null http://127.0.0.1:8000/; sleep 6; pkill -f http.server; true")
    step("ebpf-saw-8000", "journalctl -u synapse-ebpf-monitor | grep 'dport=8000' | tail -2")


def airgapped():
    step("enter-airgap", "systemctl start airgap.target; systemctl is-active airgap.target; ip route; ip rule show | head -3")
    emit("airgap-sample", file="act-exfil-http-plain.pkl", **scan(f"{CORPUS}/act-exfil-http-plain.pkl", "pickle"))
    emit("airgap-sample", file="clean-dict.pkl", **scan(f"{CORPUS}/clean-dict.pkl", "pickle"))


def receipts():
    step("verify-all", "n=0; bad=0; for r in /var/lib/synapse-chamber/runs/*/receipt.json; do n=$((n+1)); "
                       "synapse-detonate verify $r >/dev/null 2>&1 || bad=$((bad+1)); done; echo receipts=$n invalid=$bad")
    step("leftovers", "echo netns=$(ip netns list | wc -l) units=$(systemctl list-units 'synapse-chamber-*' --no-legend | wc -l); du -sh /var/lib/synapse-chamber")


for section in (corpus, fuzz, repeatability, pipelines, airgapped, receipts):
    start = time.time()
    try:
        section()
    except Exception as error:
        emit("section-error", section=section.__name__, error=repr(error))
    emit("section", section=section.__name__, secs=round(time.time() - start))
print("BENCH-DONE", flush=True)
