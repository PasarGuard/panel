"""Regenerate the installed node bridge protobufs from the panel contract."""

import importlib
from pathlib import Path

from grpc_tools import protoc
from PasarGuardNodeBridge.common import service_pb2

ROOT = Path(__file__).resolve().parent.parent
PROTO = ROOT / "proto" / "service.proto"
BRIDGE_PROTO_DIR = Path(service_pb2.__file__).resolve().parent


def main() -> None:
    result = protoc.main(
        [
            "grpc_tools.protoc",
            f"-I{PROTO.parent}",
            f"--python_out={BRIDGE_PROTO_DIR}",
            str(PROTO),
        ]
    )
    if result:
        raise SystemExit(result)

    importlib.invalidate_caches()


if __name__ == "__main__":
    main()
