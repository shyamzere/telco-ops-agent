from pathlib import Path
import snowflake.connector
from cryptography.hazmat.primitives import serialization

key_path = Path.home() / ".telco-keys" / "agent_key.p8"
private_key = serialization.load_pem_private_key(key_path.read_bytes(), password=None)
pkb = private_key.private_bytes(
    serialization.Encoding.DER,
    serialization.PrivateFormat.PKCS8,
    serialization.NoEncryption(),
)

conn = snowflake.connector.connect(
    account="XAFPDTM-VV71865",
    user="AGENT_SVC",
    private_key=pkb,
    role="AGENT_READONLY",
    warehouse="TELCO_WH",
    database="TELCO_DB",
    schema="OPS",
)
cur = conn.cursor()
cur.execute("SELECT CURRENT_USER(), CURRENT_ROLE(), COUNT(*) FROM INCIDENTS")
print(cur.fetchone())
conn.close()