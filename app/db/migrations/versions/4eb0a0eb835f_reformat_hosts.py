"""reformat hosts

Revision ID: 4eb0a0eb835f
Revises: be0c5f840473
Create Date: 2024-12-04 14:32:38.599601

"""

from alembic import op
from sqlalchemy.orm import Session
import commentjson
from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

from app.db.models import ProxyHost


# revision identifiers, used by Alembic.
revision = "4eb0a0eb835f"
down_revision = "be0c5f840473"
branch_labels = None
depends_on = None


class MigrationSettings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    xray_json: str = Field(default="./xray_config.json", validation_alias="XRAY_JSON")


migration_settings = MigrationSettings()


base_xray = {
    "log": {"loglevel": "warning"},
    "routing": {"rules": [{"ip": ["geoip:private"], "outboundTag": "BLOCK", "type": "field"}]},
    "inbounds": [
        {
            "tag": "Shadowsocks TCP",
            "listen": "0.0.0.0",
            "port": 1080,
            "protocol": "shadowsocks",
            "settings": {"clients": [], "network": "tcp,udp"},
        }
    ],
    "outbounds": [{"protocol": "freedom", "tag": "DIRECT"}, {"protocol": "blackhole", "tag": "BLOCK"}],
}


def upgrade() -> None:
    try:
        with open(migration_settings.xray_json, "r") as file:
            config = commentjson.loads(file.read())
    except Exception:
        config = base_xray

    # find current inbound tags
    inbounds = [inbound["tag"] for inbound in config["inbounds"] if "tag" in inbound]

    connection = op.get_bind()
    session = Session(bind=connection)
    try:
        # remove hosts with old inbound tag
        session.query(ProxyHost).filter(ProxyHost.inbound_tag.notin_(inbounds)).delete(synchronize_session=False)
        session.commit()
    finally:
        session.close()


def downgrade() -> None:
    pass
