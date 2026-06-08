#!/usr/bin/env python3
"""Simple OPC UA simulator server configured from YAML."""

import argparse
import random
import time
from pathlib import Path
from threading import Thread
from typing import Any, Dict, List, Optional

import yaml
from opcua import Server, ua


class SensorSimulator:
    def __init__(
        self,
        variable,
        initial_value: float,
        minimum: float,
        maximum: float,
        step: float,
        randomize: bool = True,
    ):
        self.variable = variable
        self.value = float(initial_value)
        self.minimum = float(minimum)
        self.maximum = float(maximum)
        self.step = float(step)
        self.randomize = randomize

    def update(self) -> None:
        if self.randomize:
            self.value = random.uniform(self.minimum, self.maximum)
        else:
            self.value += random.uniform(-self.step, self.step)
            self.value = max(self.minimum, min(self.maximum, self.value))
        self.variable.set_value(self.value)


class OPCUASimulator:
    def __init__(self, config: Dict[str, Any]):
        self.config = config
        self.server = Server()
        self.sensors: List[SensorSimulator] = []
        self.update_interval = config.get('server', {}).get('update_interval', 1)

        endpoint = config.get('server', {}).get('endpoint', 'opc.tcp://0.0.0.0:4840')
        namespace_uri = config.get('server', {}).get('namespace', 'http://opcua.simulator')
        self.server.set_endpoint(endpoint)
        self.idx = self.server.register_namespace(namespace_uri)
        self.server.set_server_name('OPC UA Simulator')
        self.object_node = self.server.get_objects_node()

        self._build_nodes()

    def _build_nodes(self) -> None:
        machines = self.config.get('machines', {})
        for machine_name, sensors in machines.items():
            machine_node = self.object_node.add_object(self.idx, machine_name)
            for sensor_name, sensor_def in sensors.items():
                node_id_str = sensor_def.get('node_id')
                if node_id_str:
                    node_id = ua.NodeId.from_string(node_id_str)
                else:
                    node_id = ua.NodeId(f'{machine_name}/{sensor_name}', self.idx)

                initial_value = sensor_def.get('initial_value', 0.0)
                minimum = sensor_def.get('min', initial_value)
                maximum = sensor_def.get('max', initial_value)
                step = sensor_def.get('step', 0.1)
                randomize = sensor_def.get('randomize', True)

                variable = machine_node.add_variable(node_id, sensor_name, float(initial_value))
                variable.set_writable()

                self.sensors.append(
                    SensorSimulator(
                        variable=variable,
                        initial_value=initial_value,
                        minimum=minimum,
                        maximum=maximum,
                        step=step,
                        randomize=randomize,
                    )
                )

    def start(self) -> None:
        self.server.start()
        print(f'OPC UA simulator started at {self.server.endpoint.geturl()}')
        self._run_loop()

    def stop(self) -> None:
        print('Stopping OPC UA simulator...')
        self.server.stop()

    def _run_loop(self) -> None:
        try:
            while True:
                for sensor in self.sensors:
                    sensor.update()
                time.sleep(self.update_interval)
        except KeyboardInterrupt:
            self.stop()


def load_config(path: Path) -> Dict[str, Any]:
    with path.open('r', encoding='utf-8') as f:
        return yaml.safe_load(f)


def main() -> None:
    parser = argparse.ArgumentParser(description='Run OPC UA simulator from YAML configuration.')
    parser.add_argument('--config', default='app/config.yaml', help='Path to the YAML config file')
    args = parser.parse_args()

    config_path = Path(args.config)
    config = load_config(config_path)
    simulator = OPCUASimulator(config)
    simulator.start()


if __name__ == '__main__':
    main()
