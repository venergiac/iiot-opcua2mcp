import unittest
from unittest.mock import MagicMock, patch

from src.opcua2mcp import OPCUA2MCPConverter


class TestOPCUA2MCPConverter(unittest.TestCase):
    def setUp(self):
        self.config = {
            'Machine-001': {
                'vibration': {
                    'node_id': 'ns=2;s=Machine-001/Device/Vibration',
                    'threshold': 3.5,
                    'unit': 'mm/s',
                },
                'temperature': {
                    'node_id': 'ns=2;s=Machine-001/Device/Temperature',
                    'threshold': 80.0,
                    'unit': 'C',
                },
            }
        }

    @patch('app.opcua2mcp.Client')
    def test_sensor_health_threshold_exceeded(self, mock_client):
        client_instance = mock_client.return_value
        node = MagicMock()
        node.get_value.return_value = 5.0
        client_instance.get_node.return_value = node

        converter = OPCUA2MCPConverter(
            opcua_endpoint='opc.tcp://localhost:4840',
            config=self.config,
            machine_name='Machine-001',
            cache_backend='memory',
        )

        reading = converter.read_sensor('vibration')
        self.assertEqual(reading['sensor_name'], 'vibration')
        self.assertFalse(reading['health']['within_threshold'])
        self.assertEqual(reading['health']['threshold'], 3.5)
        self.assertIn('Threshold exceeded', reading['health']['message'])

    @patch('app.opcua2mcp.Client')
    def test_get_health_status_ok_when_all_within_threshold(self, mock_client):
        client_instance = mock_client.return_value
        vibration_node = MagicMock()
        temperature_node = MagicMock()
        vibration_node.get_value.return_value = 3.0
        temperature_node.get_value.return_value = 75.0
        client_instance.get_node.side_effect = [vibration_node, temperature_node]

        converter = OPCUA2MCPConverter(
            opcua_endpoint='opc.tcp://localhost:4840',
            config=self.config,
            machine_name='Machine-001',
            cache_backend='memory',
        )

        status = converter.get_health_status(force=True)
        self.assertEqual(status['status'], 'OK')
        self.assertEqual(status['total_sensors'], 2)
        self.assertEqual(len(status['alerts']), 0)
        self.assertEqual(status['health_score'], 100.0)

    @patch('app.opcua2mcp.Client')
    def test_cache_reads_sensor_data(self, mock_client):
        client_instance = mock_client.return_value
        node = MagicMock()
        node.get_value.return_value = 2.0
        client_instance.get_node.return_value = node

        converter = OPCUA2MCPConverter(
            opcua_endpoint='opc.tcp://localhost:4840',
            config=self.config,
            machine_name='Machine-001',
            cache_backend='memory',
        )

        first = converter.read_all_sensors(force=True)
        second = converter.read_all_sensors(force=False)

        self.assertEqual(first, second)
        self.assertIn('vibration', first)
        self.assertIn('temperature', first)


if __name__ == '__main__':
    unittest.main()
