#!/usr/bin/env python3
import os
from pathlib import Path

import yaml

from opcua2mcp import OPCUA2MCPConverter


def load_config(config_path: Path) -> dict:
    if not config_path.exists():
        raise FileNotFoundError(f'Configuration file not found: {config_path}')
    with config_path.open('r', encoding='utf-8') as f:
        return yaml.safe_load(f)


if __name__ == '__main__':
    config_path = Path(os.environ.get('OPCUA_CONFIG', 'app/config.yaml'))
    config = load_config(config_path)

    machine_name = os.environ.get('MACHINE_NAME', 'Machine-001')
    opcua_endpoint = os.environ.get(
        'OPCUA_ENDPOINT', config.get('server', {}).get('endpoint', 'opc.tcp://opcua-simulator:4840')
    )
    cache_backend = os.environ.get('CACHE_BACKEND', 'redis' if os.environ.get('REDIS_URL') else 'memory')
    redis_url = os.environ.get('REDIS_URL', 'redis://redis:6379/0')
    cache_ttl = int(os.environ.get('CACHE_TTL', '30'))
    mcp_port = int(os.environ.get('MCP_PORT', '5001'))

    print(f'Loading configuration from {config_path}')
    print(f'Creating OPC UA to MCP converter for machine: {machine_name}')
    print(f'OPC UA endpoint: {opcua_endpoint}')
    print(f'Cache backend: {cache_backend}')

    converter = OPCUA2MCPConverter(
        opcua_endpoint=opcua_endpoint,
        config=config,
        machine_name=machine_name,
        cache_backend=cache_backend,
        redis_url=redis_url,
        cache_ttl=cache_ttl,
        mcp_port=mcp_port,
    )

    try:
        converter.start()
    except KeyboardInterrupt:
        print('Stopping converter...')
        converter.disconnect()
