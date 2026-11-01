"""SynapseOS detonation chamber.

A model file is data, so swapping it for an inert twin must not change what its
runtime does in the kernel. Both are loaded in identical worlds, and whatever
only the suspect does is attributable to the file.
"""
import argparse
import base64
import binascii
import hashlib
import json
import os
import re
import secrets
import shutil
import signal
import socket
import struct
import subprocess
import sys
import threading
import time
import zipfile
import zlib

STATE = "/var/lib/synapse-chamber"
SINK_PORT = 15353
INERT_TEMPLATE = "{% for m in messages %}{{ m.content }}{% endfor %}"
EXIT = {"no-divergence": 0, "divergent": 10, "exfiltration": 20, "inconclusive": 30}
SEVERITY = {"info": 0, "medium": 1, "high": 2, "critical": 3}
SENSITIVE = re.compile(r"^(/proc/(self|N)/(environ|mem|maps)|/etc/(passwd|shadow|ssh/)|/root/|/run/secrets)")

# GGUF


def _gguf_string(data, pos):
    size = struct.unpack_from("<Q", data, pos)[0]
    if pos + 8 + size > len(data):
        raise ValueError("GGUF string overruns the file")
    return data[pos + 8 : pos + 8 + size], pos + 8 + size


_FIXED = {0: 1, 1: 1, 2: 2, 3: 2, 4: 4, 5: 4, 6: 4, 7: 1, 10: 8, 11: 8, 12: 8}


def _gguf_value(data, pos, kind):
    if kind in _FIXED:
        return pos + _FIXED[kind]
    if kind == 8:
        return _gguf_string(data, pos)[1]
    if kind == 9:
        inner, count = struct.unpack_from("<IQ", data, pos)
        pos += 12
        if count > len(data):
            raise ValueError("GGUF array overruns the file")
        for _ in range(count):
            pos = _gguf_value(data, pos, inner)
        return pos
    raise ValueError(f"unknown GGUF value type {kind}")


def parse_gguf(data):
    if data[:4] != b"GGUF":
        raise ValueError("not a GGUF file")
    version, tensors, count = struct.unpack_from("<IQQ", data, 4)
    if version not in (2, 3) or tensors > len(data) or count > len(data):
        raise ValueError("implausible GGUF header")
    pos, kvs, alignment = 24, [], 32
    for _ in range(count):
        start = pos
        key, pos = _gguf_string(data, pos)
        kind = struct.unpack_from("<I", data, pos)[0]
        pos += 4
        value_at = pos
        pos = _gguf_value(data, pos, kind)
        kvs.append((key.decode("utf-8", "replace"), kind, start, value_at, pos))
        if key == b"general.alignment":
            alignment = struct.unpack_from("<I", data, value_at)[0]
    if alignment == 0 or alignment % 2:
        raise ValueError("bad GGUF alignment")
    kv_end = pos
    for _ in range(tensors):
        _, pos = _gguf_string(data, pos)
        dims = struct.unpack_from("<I", data, pos)[0]
        pos += 4 + dims * 8 + 4 + 8
    data_start = pos + (-pos % alignment)
    if data_start > len(data):
        data_start = len(data)
    return kvs, kv_end, pos, data_start, alignment


def chat_template(data):
    for key, kind, _, value_at, _ in parse_gguf(data)[0]:
        if key == "tokenizer.chat_template" and kind == 8:
            return _gguf_string(data, value_at)[0].decode("utf-8", "replace")
    return INERT_TEMPLATE


def gguf_twin(data):
    """The same model with its active content, the chat templates, replaced."""
    kvs, kv_end, info_end, data_start, alignment = parse_gguf(data)
    out = bytearray(data[:24])
    inert = INERT_TEMPLATE.encode()
    for key, kind, start, value_at, end in kvs:
        if key.startswith("tokenizer.chat_template") and kind == 8:
            out += data[start:value_at] + struct.pack("<Q", len(inert)) + inert
        else:
            out += data[start:end]
    out += data[kv_end:info_end]
    out += b"\0" * (-len(out) % alignment)
    return bytes(out) + data[data_start:]


# Twins


def inert_torch(path, target):
    """Replace the pickle stream of a torch zip archive, keeping everything else."""
    with zipfile.ZipFile(path) as src, zipfile.ZipFile(target, "w", zipfile.ZIP_STORED) as dst:
        replaced = False
        for item in src.infolist():
            if item.filename.endswith("/data.pkl") or item.filename == "data.pkl":
                dst.writestr(item.filename, b"\x80\x02}q\x00.")
                replaced = True
            else:
                dst.writestr(item.filename, src.read(item))
    if not replaced:
        raise ValueError("no data.pkl in archive")


def make_twin(path, target, runtime):
    if runtime == "pickle":
        with open(target, "wb") as f:
            f.write(b"\x80\x02}q\x00.")
    elif runtime == "torch":
        inert_torch(path, target)
    elif runtime in ("jinja", "llama"):
        with open(path, "rb") as f:
            data = f.read()
        with open(target, "wb") as f:
            f.write(gguf_twin(data))
    else:
        raise ValueError(runtime)


def run_loader(runtime, path):
    """Runs inside the chamber. This is the code a real pipeline would run."""
    if runtime == "pickle":
        import pickle

        with open(path, "rb") as f:
            pickle.load(f)
    elif runtime == "torch":
        import torch

        torch.load(path, weights_only=False)
    elif runtime == "jinja":
        import jinja2

        with open(path, "rb") as f:
            template = chat_template(f.read())
        jinja2.Environment().from_string(template).render(
            messages=[{"role": "user", "content": "hello"}], bos_token="", eos_token=""
        )


# Honey world


def honey_world(root):
    upper = "ABCDEFGHIJKLMNOPQRSTUVWXYZ234567"
    tokens = {
        "aws_key": "AKIA" + "".join(secrets.choice(upper) for _ in range(16)),
        "aws_secret": base64.b64encode(secrets.token_bytes(30)).decode(),
        "openai": "sk-" + secrets.token_hex(24),
        "kube": secrets.token_urlsafe(32),
        "ssh": base64.b64encode(secrets.token_bytes(48)).decode(),
    }
    files = {
        ".aws/credentials": f"[default]\naws_access_key_id = {tokens['aws_key']}\n"
        f"aws_secret_access_key = {tokens['aws_secret']}\n",
        ".ssh/id_ed25519": "-----BEGIN OPENSSH PRIVATE KEY-----\n"
        f"{tokens['ssh']}\n-----END OPENSSH PRIVATE KEY-----\n",
        ".env": f"OPENAI_API_KEY={tokens['openai']}\n",
        ".kube/config": f"users:\n- name: admin\n  user:\n    token: {tokens['kube']}\n",
    }
    for name, body in files.items():
        path = os.path.join(root, name)
        os.makedirs(os.path.dirname(path), exist_ok=True, mode=0o755)
        with open(path, "w") as f:
            f.write(body)
        os.chmod(path, 0o644)
    env = {
        "HOME": "/home/analyst",
        "USER": "analyst",
        "PATH": "/run/current-system/sw/bin",
        "AWS_ACCESS_KEY_ID": tokens["aws_key"],
        "AWS_SECRET_ACCESS_KEY": tokens["aws_secret"],
        "OPENAI_API_KEY": tokens["openai"],
    }
    return tokens, sorted(files), env


def decoded_views(blob):
    views = [blob, blob.replace(b".", b"")]
    text = blob.decode("latin-1")
    joined = text.replace(".", "")
    for pattern, decode in (
        (r"[A-Za-z0-9+/_-]{16,}={0,2}", lambda s: base64.b64decode(s + "=" * (-len(s) % 4), altchars=b"-_" if "-" in s or "_" in s else None)),
        (r"[0-9a-fA-F]{16,}", lambda s: binascii.unhexlify(s[: len(s) & ~1])),
        (r"[A-Z2-7a-z]{16,}={0,6}", lambda s: base64.b32decode(s.upper() + "=" * (-len(s) % 8))),
    ):
        for source in (text, joined):
            for match in re.findall(pattern, source):
                try:
                    raw = decode(match)
                except (ValueError, binascii.Error):
                    continue
                views.append(raw)
                try:
                    views.append(zlib.decompress(raw))
                except zlib.error:
                    pass
    return views


def leaked(tokens, blob):
    views = decoded_views(blob)
    names = []
    for name, token in tokens.items():
        needle = token.encode()
        if any(needle in view or needle.lower() in view.lower() for view in views):
            names.append(name)
    return names


# Fake internet


def dns_reply(query):
    pos, labels = 12, []
    while pos < len(query) and query[pos]:
        size = query[pos]
        labels.append(query[pos + 1 : pos + 1 + size].decode("latin-1"))
        pos += size + 1
    question = query[12 : pos + 5]
    answer = b"\xc0\x0c\x00\x01\x00\x01\x00\x00\x00\x3c\x00\x04" + socket.inet_aton("198.51.100.7")
    return ".".join(labels), query[:2] + b"\x81\x80\x00\x01\x00\x01\x00\x00\x00\x00" + question + answer


def sink(log, ready):
    lock = threading.Lock()
    out = open(log, "a", buffering=1)

    def record(**event):
        with lock:
            out.write(json.dumps(event) + "\n")

    def tcp_client(conn):
        try:
            raw = conn.getsockopt(socket.SOL_IP, 80, 16)
            port, addr = struct.unpack("!H", raw[2:4])[0], socket.inet_ntoa(raw[4:8])
            conn.settimeout(2)
            blob = b""
            try:
                while len(blob) < 1 << 20:
                    chunk = conn.recv(65536)
                    if not chunk:
                        break
                    blob += chunk
                    if b"\r\n\r\n" in blob:
                        conn.sendall(b"HTTP/1.1 200 OK\r\nContent-Length: 2\r\nConnection: close\r\n\r\nok")
                        conn.settimeout(0.5)
            except (TimeoutError, OSError):
                pass
            record(proto="tcp", dst=f"{addr}:{port}", data=base64.b64encode(blob).decode())
        finally:
            conn.close()

    def tcp():
        server = socket.socket()
        server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        server.bind(("0.0.0.0", SINK_PORT))
        server.listen(64)
        open(ready, "w").close()
        while True:
            conn, _ = server.accept()
            threading.Thread(target=tcp_client, args=(conn,), daemon=True).start()

    threading.Thread(target=tcp, daemon=True).start()
    udp = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    udp.bind(("0.0.0.0", SINK_PORT))
    while True:
        blob, peer = udp.recvfrom(65535)
        try:
            name, reply = dns_reply(blob)
            udp.sendto(reply, peer)
            record(proto="dns", dst=name, data=base64.b64encode(name.encode()).decode())
        except (IndexError, ValueError, OSError):
            record(proto="udp", dst="", data=base64.b64encode(blob).decode())


# Tracing


PROBES = [
    ("syscalls:sys_enter_openat", 'printf("open\\t%d\\t%s\\n", args.flags, str(args.filename));'),
    ("syscalls:sys_enter_execve", 'printf("exec\\t0\\t%s\\n", str(args.filename));'),
    ("syscalls:sys_enter_execveat", 'printf("exec\\t0\\t%s\\n", str(args.filename));'),
    ("syscalls:sys_enter_socket", 'printf("socket\\t%d\\t%d\\n", args.family, args.type & 15);'),
    ("syscalls:sys_enter_connect", 'printf("connect\\t0\\t\\n");'),
    ("syscalls:sys_enter_bind", 'printf("bind\\t0\\t\\n");'),
    ("syscalls:sys_enter_memfd_create", 'printf("memfd\\t0\\t%s\\n", str(args.uname));'),
    ("syscalls:sys_enter_ptrace", 'printf("ptrace\\t%d\\t\\n", args.request);'),
    ("syscalls:sys_enter_unlinkat", 'printf("unlink\\t0\\t%s\\n", str(args.pathname));'),
    ("syscalls:sys_enter_mprotect", 'printf("mprotect\\t%d\\t\\n", args.prot);'),
]


def bpf_program(cgroup):
    guard = f'cgroup == cgroupid("{cgroup}")'
    body = "\n".join(f"tracepoint:{probe} /{guard}/ {{ {action} }}" for probe, action in PROBES)
    return 'config = { max_strlen = 200 }\nBEGIN { printf("READY\\n"); }\n' + body + "\n"


def wait_for(check, timeout, what):
    deadline = time.time() + timeout
    while time.time() < deadline:
        if check():
            return
        time.sleep(0.05)
    raise RuntimeError(f"timed out waiting for {what}")


def sh(*cmd, **kwargs):
    return subprocess.run(cmd, check=True, capture_output=True, text=True, **kwargs).stdout.strip()


def detonate(name, model, runtime, rundir, world, opts):
    """One arm: a fresh world, a held process, the tracer attached, then release."""
    home, env = world
    netns, unit = f"syn-{name}", f"synapse-chamber-{name}"
    arm = os.path.join(rundir, name)
    os.makedirs(arm)
    gate, ready, sink_log = f"{arm}/gate", f"{arm}/sink-ready", f"{arm}/sink.jsonl"
    os.mkfifo(gate, 0o644)
    os.chmod(arm, 0o755)

    sh("ip", "netns", "add", netns)
    sinker = target = tracer = None
    try:
        rules = f"""table inet world {{
          chain output {{ type nat hook output priority -100;
            meta l4proto tcp redirect to :{SINK_PORT}
            meta l4proto udp redirect to :{SINK_PORT}
          }}
        }}"""
        ns = ["ip", "netns", "exec", netns]
        sh(*ns, "ip", "link", "set", "lo", "up")
        sh(*ns, "ip", "route", "add", "local", "0.0.0.0/0", "dev", "lo")
        subprocess.run([*ns, "nft", "-f", "-"], input=rules, text=True, check=True)
        sinker = subprocess.Popen([*ns, sys.executable, os.path.abspath(__file__), "_sink", sink_log, ready])
        wait_for(lambda: os.path.exists(ready), 15, "the fake internet")

        loader = (
            ["/run/current-system/sw/bin/llama-cli", "-m", "/work/model", "-p", "Hello", "-n", "8"]
            if runtime == "llama"
            else [sys.executable, os.path.abspath(__file__), "_load", runtime, "/work/model"]
        )
        props = [
            "DynamicUser=yes",
            f"NetworkNamespacePath=/run/netns/{netns}",
            f"MemoryMax={opts.memory}",
            "MemorySwapMax=0",
            "TasksMax=512",
            f"RuntimeMaxSec={opts.timeout}",
            "ProtectSystem=strict",
            "PrivateTmp=yes",
            "PrivateDevices=yes",
            "ProtectKernelTunables=yes",
            "ProtectKernelModules=yes",
            "ProtectKernelLogs=yes",
            "ProtectControlGroups=yes",
            "NoNewPrivileges=yes",
            "CapabilityBoundingSet=",
            "SystemCallArchitectures=native",
            "TemporaryFileSystem=/home:ro",
            f"BindReadOnlyPaths={home}:/home/analyst",
            f"BindReadOnlyPaths={model}:/work/model",
            f"BindReadOnlyPaths={gate}:/gate",
            "WorkingDirectory=/tmp",
        ]
        cmd = ["systemd-run", "--quiet", "--collect", "--wait", f"--unit={unit}"]
        cmd += [f"--setenv={k}={v}" for k, v in env.items()]
        cmd += [f"--property={p}" for p in props]
        cmd += ["--", "/bin/sh", "-c", 'read -r _ < /gate; exec "$@"', "chamber", *loader]
        target = subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

        def cgroup():
            return sh("systemctl", "show", "-p", "ControlGroup", "--value", f"{unit}.service")

        wait_for(cgroup, 15, "the chamber unit")
        path = "/sys/fs/cgroup" + cgroup()
        with open(f"{arm}/probes.bt", "w") as f:
            f.write(bpf_program(path))
        err = open(f"{arm}/bpftrace.err", "w+")
        tracer = subprocess.Popen(
            ["bpftrace", "-B", "line", f"{arm}/probes.bt"], stdout=subprocess.PIPE, stderr=err, text=True
        )
        attached = threading.Event()
        lines = []

        def read_trace():
            for line in tracer.stdout:
                if line.startswith("READY"):
                    attached.set()
                else:
                    lines.append(line.rstrip("\n"))

        threading.Thread(target=read_trace, daemon=True).start()
        if not attached.wait(90):
            tracer.kill()
            detail = subprocess.run(
                ["bpftrace", "-v", "-B", "line", f"{arm}/probes.bt"], capture_output=True, text=True, timeout=120
            )
            raise RuntimeError(f"the tracer did not attach: {detail.stderr[-6000:]}")

        # The process has been held at the gate until now, so no event precedes the tracer.
        def release():
            try:
                fd = os.open(gate, os.O_WRONLY | os.O_NONBLOCK)
            except OSError:
                return False
            os.write(fd, b"go\n")
            os.close(fd)
            return True

        wait_for(release, 15, "the chamber gate")
        status = target.wait(opts.timeout + 30)
        time.sleep(1)
        tracer.send_signal(signal.SIGINT)
        tracer.wait(30)
        err.seek(0)
        lost = sum(int(n) for n in re.findall(r"Lost (\d+) events", err.read()))
        return lines, read_sink(sink_log), status, lost
    finally:
        for proc in (target, tracer, sinker):
            if proc and proc.poll() is None:
                proc.kill()
        subprocess.run(["systemctl", "stop", f"{unit}.service"], capture_output=True)
        subprocess.run(["ip", "netns", "del", netns], capture_output=True)


def read_sink(path):
    if not os.path.exists(path):
        return []
    with open(path) as f:
        return [json.loads(line) for line in f]


# Behaviour


def normal_path(path):
    path = re.sub(r"/proc/\d+", "/proc/N", path)
    return re.sub(r"(/tmp/|/var/tmp/)[^/]+", r"\1*", path)


def behaviours(lines, sink_events, home_files):
    """Reduce a trace to a set. Counts and ordering depend on size, so they are dropped."""
    found = set()
    honey = {f"/home/analyst/{name}" for name in home_files}
    for line in lines:
        parts = line.split("\t")
        if len(parts) != 3:
            continue
        kind, number, text = parts
        number = int(number)
        if kind == "open":
            path = normal_path(text)
            writing = number & 3 or number & 0o100
            if path in honey:
                found.add(("high", "honey-read", path))
            elif SENSITIVE.match(path):
                found.add(("high", "sensitive-read", path))
            elif writing and not path.startswith("/dev/"):
                found.add(("medium", "write", path))
            else:
                found.add(("info", "read", path))
        elif kind == "exec":
            found.add(("high", "exec", normal_path(text)))
        elif kind == "socket" and number in (2, 10, 17):
            found.add(("medium", "socket", {2: "inet", 10: "inet6", 17: "packet"}[number]))
        elif kind in ("connect", "bind"):
            found.add(("medium", kind, ""))
        elif kind == "memfd":
            found.add(("high", "memfd", ""))
        elif kind == "ptrace":
            found.add(("high", "ptrace", ""))
        elif kind == "unlink":
            found.add(("medium", "unlink", normal_path(text)))
        elif kind == "mprotect" and number & 4:
            found.add(("medium", "exec-memory", ""))
    for event in sink_events:
        target = event["dst"]
        if event["proto"] == "dns":
            target = ".".join(target.split(".")[-2:])
        found.add(("high", event["proto"], target))
    return found


def judge(twin, suspect, twin_status, suspect_status, lost, exfil):
    divergence = suspect - twin
    if suspect_status != 0 and twin_status == 0:
        divergence.add(("high", "runtime-failure", f"status {suspect_status}"))
    for name in exfil:
        divergence.add(("critical", "exfiltration", name))
    ranked = sorted(divergence, key=lambda b: (-SEVERITY[b[0]], b[1], b[2]))
    worst = max((SEVERITY[b[0]] for b in ranked), default=0)
    if worst == 3:
        verdict = "exfiltration"
    elif worst >= 1:
        verdict = "divergent"
    elif lost or twin_status != 0:
        verdict = "inconclusive"
    else:
        verdict = "no-divergence"
    # Bytes read are often version noise, so a digest covers what the verdict rests on.
    material = [list(b) for b in ranked if SEVERITY[b[0]] >= 1]
    digest = hashlib.sha256(canonical(material)).hexdigest()
    return verdict, ranked, digest


# Receipts


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":")).encode()


def chain(lines, head=""):
    for line in lines:
        head = hashlib.sha256((head + line).encode()).hexdigest()
    return head


def sha256_file(path):
    digest = hashlib.sha256()
    with open(path, "rb") as f:
        for block in iter(lambda: f.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def signing_key():
    key, public = f"{STATE}/receipt.key", f"{STATE}/receipt.pub"
    if not os.path.exists(key):
        sh("openssl", "genpkey", "-algorithm", "ed25519", "-out", key)
        os.chmod(key, 0o600)
        sh("openssl", "pkey", "-in", key, "-pubout", "-out", public)
    with open(public) as f:
        return key, f.read()


def lab_identity():
    version = json.loads(sh("/run/current-system/sw/bin/nixos-version", "--json"))
    return {
        "system": os.readlink("/run/current-system"),
        "kernel": os.uname().release,
        "revision": version.get("configurationRevision"),
        "nixpkgs": version.get("nixpkgsRevision"),
    }


def sign(receipt, rundir):
    key, public = signing_key()
    receipt["lab"]["public_key"] = public
    message = f"{rundir}/receipt.msg"
    with open(message, "wb") as f:
        f.write(canonical(receipt))
    sig = f"{rundir}/receipt.sig"
    sh("openssl", "pkeyutl", "-sign", "-rawin", "-inkey", key, "-in", message, "-out", sig)
    with open(sig, "rb") as f:
        return base64.b64encode(f.read()).decode()


def verify(path):
    with open(path) as f:
        receipt = json.load(f)
    signature = receipt.pop("signature")
    work = f"{path}.verify"
    os.makedirs(work, exist_ok=True)
    try:
        with open(f"{work}/msg", "wb") as f:
            f.write(canonical(receipt))
        with open(f"{work}/sig", "wb") as f:
            f.write(base64.b64decode(signature))
        with open(f"{work}/pub", "w") as f:
            f.write(receipt["lab"]["public_key"])
        run = subprocess.run(
            ["openssl", "pkeyutl", "-verify", "-pubin", "-inkey", f"{work}/pub", "-rawin",
             "-in", f"{work}/msg", "-sigfile", f"{work}/sig"],
            capture_output=True,
        )
    finally:
        shutil.rmtree(work)
    if run.returncode != 0:
        print("signature: INVALID")
        return 1
    print(f"signature: valid\nverdict: {receipt['verdict']}\nmodel: {receipt['model']['sha256']}")
    print(f"lab: {receipt['lab']['system']}")
    trace = os.path.join(os.path.dirname(path), "suspect.trace")
    if os.path.exists(trace):
        with open(trace) as f:
            head = chain(f.read().splitlines())
        if head != receipt["trace"]["suspect_head"]:
            print("trace: DOES NOT MATCH")
            return 1
        print("trace: matches")
    return 0


# Commands


def scan(opts):
    source = os.path.realpath(opts.model)
    if ":" in source:
        raise SystemExit("the model path must not contain a colon")
    run_id = secrets.token_hex(4)
    rundir = f"{STATE}/runs/{run_id}"
    os.makedirs(rundir)
    os.chmod(rundir, 0o755)
    os.chmod(f"{STATE}/runs", 0o755)
    os.chmod(STATE, 0o755)

    suspect, twin = f"{rundir}/suspect.bin", f"{rundir}/twin.bin"
    shutil.copyfile(source, suspect)
    make_twin(suspect, twin, opts.runtime)
    os.chmod(suspect, 0o644)
    os.chmod(twin, 0o644)

    home = f"{rundir}/home"
    os.makedirs(home, mode=0o755)
    tokens, home_files, env = honey_world(home)
    world = (home, env)

    twin_lines, twin_sink, twin_status, twin_lost = detonate(f"{run_id}-t", twin, opts.runtime, rundir, world, opts)
    sus_lines, sus_sink, sus_status, sus_lost = detonate(f"{run_id}-s", suspect, opts.runtime, rundir, world, opts)

    exfil = sorted({n for e in sus_sink for n in leaked(tokens, base64.b64decode(e["data"]))})
    verdict, ranked, digest = judge(
        behaviours(twin_lines, twin_sink, home_files),
        behaviours(sus_lines, sus_sink, home_files),
        twin_status, sus_status, twin_lost + sus_lost, exfil,
    )

    for name, lines in (("twin", twin_lines), ("suspect", sus_lines)):
        with open(f"{rundir}/{name}.trace", "w") as f:
            f.write("".join(line + "\n" for line in lines))
    receipt = {
        "schema": "synapse-chamber/1",
        "model": {"sha256": sha256_file(suspect), "size": os.path.getsize(suspect), "runtime": opts.runtime},
        "twin": {"sha256": sha256_file(twin)},
        "lab": lab_identity(),
        "trace": {
            "suspect_events": len(sus_lines), "twin_events": len(twin_lines),
            "suspect_head": chain(sus_lines), "twin_head": chain(twin_lines),
            "lost": twin_lost + sus_lost,
        },
        "exit": {"suspect": sus_status, "twin": twin_status},
        "verdict": verdict,
        "behaviour_digest": digest,
        "findings": [{"severity": s, "kind": k, "target": t} for s, k, t in ranked if SEVERITY[s] >= 1],
    }
    receipt["signature"] = sign(receipt, rundir)
    path = f"{rundir}/receipt.json"
    with open(path, "w") as f:
        json.dump(receipt, f, indent=2)
    for leftover in (suspect, twin, f"{rundir}/receipt.msg", f"{rundir}/receipt.sig"):
        os.remove(leftover)
    shutil.rmtree(home)
    print(f"verdict: {verdict}")
    print(f"digest:  {digest}")
    for item in receipt["findings"]:
        print(f"  {item['severity']:<9}{item['kind']:<15}{item['target']}")
    print(f"receipt: {path}")
    return EXIT[verdict]


def main():
    if len(sys.argv) > 1 and sys.argv[1] == "_load":
        run_loader(sys.argv[2], sys.argv[3])
        return 0
    if len(sys.argv) > 1 and sys.argv[1] == "_sink":
        sink(sys.argv[2], sys.argv[3])
        return 0
    parser = argparse.ArgumentParser(prog="synapse-detonate", description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    scan_args = commands.add_parser("scan", help="detonate a model file against its inert twin")
    scan_args.add_argument("model")
    scan_args.add_argument("--runtime", required=True, choices=["pickle", "torch", "jinja", "llama"])
    scan_args.add_argument("--memory", default="4G")
    scan_args.add_argument("--timeout", type=int, default=120)
    verify_args = commands.add_parser("verify", help="check a receipt's signature and trace")
    verify_args.add_argument("receipt")
    opts = parser.parse_args()
    return scan(opts) if opts.command == "scan" else verify(opts.receipt)


if __name__ == "__main__":
    sys.exit(main())
