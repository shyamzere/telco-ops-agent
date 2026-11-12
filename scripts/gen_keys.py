from pathlib import Path
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.hazmat.primitives import serialization

out = Path.home() / ".telco-keys"
out.mkdir(exist_ok=True)
key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
(out / "agent_key.p8").write_bytes(key.private_bytes(
    serialization.Encoding.PEM,
    serialization.PrivateFormat.PKCS8,
    serialization.NoEncryption()))
pub = key.public_key().public_bytes(
    serialization.Encoding.PEM,
    serialization.PublicFormat.SubjectPublicKeyInfo).decode()
print("".join(l for l in pub.splitlines() if "KEY" not in l))