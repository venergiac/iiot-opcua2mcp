#!/usr/bin/env python3
"""Expose OPC UA sensor readings as MCP tools using FastMCP."""

import asyncio
import json
from datetime import datetime
from typing import Any, Dict, List, Optional

from mcp.server import FastMCP
from opcua import Client
from starlette.responses import JSONResponse

try:
    import redis as redis_lib
except ImportError:
    redis_lib = None


SensorDefinition = Dict[str, Any]
MachineSensorConfig = Dict[str, SensorDefinition]
MultiMachineConfig = Dict[str, MachineSensorConfig]


class SensorCache:
    def __init__(
        self,
        backend: str = 'memory',
        redis_url: Optional[str] = None,
        prefix: str = 'opcua',
    ):
        self.backend = backend
        self.prefix = prefix
        self.redis_url = redis_url
        self.store: Dict[str, Any] = {}
        self.redis_client = None

        if backend == 'redis':
            if redis_lib is None:
                raise ImportError('Redis backend requested but redis package is not installed.')
            redis_url = redis_url or 'redis://localhost:6379/0'
            self.redis_client = redis_lib.from_url(redis_url)

    def _key(self, key: str) -> str:
        return f'{self.prefix}:{key}'

    def set(self, key: str, value: Any, ttl: Optional[int] = None) -> None:
        cache_key = self._key(key)
        if self.backend == 'redis' and self.redis_client is not None:
            payload = json.dumps(value, default=str)
            self.redis_client.set(cache_key, payload, ex=ttl)
        else:
            self.store[cache_key] = {
                'value': value,
                'expires_at': datetime.utcnow().timestamp() + ttl if ttl else None,
            }

    def get(self, key: str) -> Optional[Any]:
        cache_key = self._key(key)
        if self.backend == 'redis' and self.redis_client is not None:
            raw = self.redis_client.get(cache_key)
            if raw is None:
                return None
            return json.loads(raw)

        entry = self.store.get(cache_key)
        if not entry:
            return None

        expires_at = entry.get('expires_at')
        if expires_at and datetime.utcnow().timestamp() > expires_at:
            self.store.pop(cache_key, None)
            return None

        return entry['value']

    def get_all(self) -> Dict[str, Any]:
        if self.backend == 'redis' and self.redis_client is not None:
            result: Dict[str, Any] = {}
            for raw_key in self.redis_client.keys(self._key('*')):
                key = raw_key.decode('utf-8')
                value = self.redis_client.get(key)
                if value is not None:
                    result[key] = json.loads(value)
            return result

        result = {}
        for key, entry in self.store.items():
            expires_at = entry.get('expires_at')
            if expires_at and datetime.utcnow().timestamp() > expires_at:
                continue
            result[key] = entry['value']
        return result


class OPCUA2MCPConverter:
    def __init__(
        self,
        opcua_endpoint: str,
        config: MultiMachineConfig,
        machine_name: str,
        cache_backend: str = 'memory',
        redis_url: Optional[str] = None,
        cache_ttl: int = 30,
        mcp_host: str = '0.0.0.0',
        mcp_port: int = 5001,
        mount_path: str = '/mcp',
    ):
        self.opcua_endpoint = opcua_endpoint
        self.machine_name = machine_name
        self.cache_ttl = cache_ttl
        self.machine_sensors = self._load_machine_config(config, machine_name)
        self.cache = SensorCache(cache_backend, redis_url, prefix=f'opcua:{machine_name}')
        self.client = Client(opcua_endpoint)
        self.mcp_server = self._build_mcp_server(mcp_host, mcp_port, mount_path)

    def _load_machine_config(
        self,
        config: MultiMachineConfig,
        machine_name: str,
    ) -> MachineSensorConfig:
        if 'machines' in config:
            config = config['machines']

        sensors = config.get(machine_name)
        if sensors is None:
            raise ValueError(f'Machine configuration for "{machine_name}" not found.')
        if not isinstance(sensors, dict):
            raise ValueError('Sensor configuration for machine must be a dictionary.')
        return sensors

    def connect(self, timeout: int = 10) -> None:
        self.client.timeout = timeout
        self.client.connect()

    def disconnect(self) -> None:
        try:
            self.client.disconnect()
        except Exception:
            pass

    def _sensor_cache_key(self, sensor_name: str) -> str:
        return f'sensor:{sensor_name}'

    def _all_cache_key(self) -> str:
        return 'sensor:all'

    def read_sensor(self, sensor_name: str) -> Dict[str, Any]:
        sensor_def = self.machine_sensors.get(sensor_name)
        if sensor_def is None:
            raise KeyError(f'Sensor "{sensor_name}" is not configured for machine "{self.machine_name}".')

        node_id = sensor_def.get('node_id') or sensor_def.get('node')
        if not node_id:
            raise ValueError(f'Sensor configuration for "{sensor_name}" is missing a node_id or node field.')

        node = self.client.get_node(node_id)
        raw_value = node.get_value()
        timestamp = datetime.utcnow().isoformat()
        reading = {
            'sensor_name': sensor_name,
            'value': raw_value,
            'unit': sensor_def.get('unit'),
            'threshold': sensor_def.get('threshold'),
            'timestamp': timestamp,
        }
        reading['health'] = self._sensor_health(sensor_name, raw_value, sensor_def)
        self.cache.set(self._sensor_cache_key(sensor_name), reading, ttl=self.cache_ttl)
        return reading

    def read_all_sensors(self, force: bool = False) -> Dict[str, Any]:
        if not force:
            cached = self.cache.get(self._all_cache_key())
            if cached is not None:
                return cached

        readings: Dict[str, Any] = {}
        for sensor_name in self.machine_sensors.keys():
            try:
                readings[sensor_name] = self.read_sensor(sensor_name)
            except Exception as exc:
                readings[sensor_name] = {
                    'sensor_name': sensor_name,
                    'error': str(exc),
                    'timestamp': datetime.utcnow().isoformat(),
                }

        self.cache.set(self._all_cache_key(), readings, ttl=self.cache_ttl)
        return readings

    def _sensor_health(
        self,
        sensor_name: str,
        value: Any,
        sensor_def: SensorDefinition,
    ) -> Dict[str, Any]:
        threshold = sensor_def.get('threshold')
        if threshold is None:
            return {
                'within_threshold': True,
                'score': 100.0,
                'message': 'No threshold configured.',
            }

        try:
            value_float = float(value)
        except (TypeError, ValueError):
            return {
                'within_threshold': False,
                'score': 0.0,
                'message': 'Non-numeric sensor value.',
            }

        within_threshold = value_float <= float(threshold)
        if within_threshold:
            score = 100.0
            message = 'Within threshold.'
        else:
            deviation = (value_float - float(threshold)) / float(threshold)
            score = max(0.0, round(max(0.0, 100.0 - deviation * 100.0), 2))
            message = 'Threshold exceeded.'

        return {
            'within_threshold': within_threshold,
            'threshold': threshold,
            'score': score,
            'message': message,
        }

    def get_cached_readings(self) -> Dict[str, Any]:
        return self.cache.get_all()

    def get_health_status(self, force: bool = False) -> Dict[str, Any]:
        readings = self.read_all_sensors(force=force)
        scores = [
            reading.get('health', {}).get('score', 0.0)
            for reading in readings.values()
            if isinstance(reading, dict)
        ]
        average_health = round(sum(scores) / len(scores), 2) if scores else 0.0
        alerts = [
            {
                'sensor_name': name,
                'value': reading.get('value'),
                'threshold': reading.get('health', {}).get('threshold'),
                'message': reading.get('health', {}).get('message'),
            }
            for name, reading in readings.items()
            if isinstance(reading, dict)
            and reading.get('health', {}).get('within_threshold') is False
        ]
        status = 'OK' if not alerts else 'DEGRADED' if len(alerts) < len(readings) else 'ALERT'

        return {
            'machine_name': self.machine_name,
            'status': status,
            'health_score': average_health,
            'alerts': alerts,
            'total_sensors': len(self.machine_sensors),
            'sensor_readings': readings,
            'timestamp': datetime.utcnow().isoformat(),
        }

    def _build_mcp_server(
        self,
        host: str,
        port: int,
        mount_path: str,
    ) -> FastMCP:
        server = FastMCP(
            name=f'OPCUA2MCP-{self.machine_name}',
            instructions=f'OPC UA to MCP converter for {self.machine_name}.',
            host=host,
            port=port,
            mount_path=mount_path,
            streamable_http_path=mount_path,
            message_path=f'{mount_path}/messages/',
            json_response=True,
        )

        server.add_tool(
            self.get_health_status,
            name='health.check',
            title='Machine Health Check',
            description=f'Return the current health score and alerts for {self.machine_name}.',
        )

        server.add_tool(
            self.read_all_sensors,
            name='read.sensors',
            title='Read All Sensors',
            description=f'Return the latest sensor values for {self.machine_name}.',
        )

        @server.custom_route('/health', methods=['GET'])
        async def health_route(request):
            return JSONResponse(self.get_health_status(force=True))

        @server.custom_route('/sensors', methods=['GET'])
        async def sensors_route(request):
            return JSONResponse(self.read_all_sensors(force=True))

        @server.custom_route('/cache', methods=['GET'])
        async def cache_route(request):
            return JSONResponse(self.get_cached_readings())

        return server

    def start(self) -> None:
        self.connect()
        asyncio.run(self.mcp_server.run_streamable_http_async())
