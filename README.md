
![github](https://img.shields.io/badge/github-repo-blue?logo=github)
![ai](https://img.shields.io/badge/physical_ai-iiot-green)
[![followme](https://img.shields.io/badge/followme-venergiac-red)](https://venergiac.substack.com/)

# OPCUA2MCP IIoT Bridge

This repository provides an end-to-end Industrial IoT prototype that converts OPC UA sensor data into MCP-compatible tools and exposes machine health via both HTTP and MCP.

![/logo.png](/logo.png)

## What is `opcua2mcp`?

`opcua2mcp` is the core bridge module in `src/opcua2mcp.py`.
It connects to an OPC UA server, reads sensor values defined in YAML configuration, evaluates sensor health against configurable thresholds, caches readings, and publishes the results through a `FastMCP` server.

The design is ideal for IIoT deployments that need:
- OPC UA data ingestion from equipment simulators or real PLCs
- MCP tool exposure for model context interoperability
- machine health scoring and alert generation
- optional Redis caching for faster repeated reads

## Architecture

- `app/app.py` — start-up script that loads `app/config.yaml`, reads environment variables, and launches the converter.
- `src/opcua2mcp.py` — core converter implementation that builds the MCP server and sensor health logic.
- `app/opcua_simulator.py` — OPC UA simulator that can be configured from YAML and serves variable sensor values.
- `docker-compose.yml` — orchestrates the OPC UA simulator, two machine-specific converter containers, and Redis.

## Configuration

The OPC UA simulator and sensor definitions are stored in `app/config.yaml`.
Example structure:

```yaml
server:
  endpoint: opc.tcp://0.0.0.0:4840
  namespace: http://opcua.simulator
  update_interval: 2

machines:
  Machine-001:
    vibration:
      node_id: ns=2;s=Machine-001/Device/Vibration
      unit: mm/s
      threshold: 3.5
      initial_value: 2.2
      min: 0.5
      max: 5.0
      step: 0.25
      randomize: true
    temperature:
      node_id: ns=2;s=Machine-001/Device/Temperature
      unit: C
      threshold: 80.0
      initial_value: 68.0
      min: 50.0
      max: 92.0
      step: 1.5
      randomize: true
```

Each machine has named sensors with:
- `node_id` or generated node identifier
- `unit`
- `threshold` for health evaluation
- optional simulation parameters: `initial_value`, `min`, `max`, `step`, `randomize`

## Running the stack

Install dependencies:

```bash
pip install -r requirements.txt
```

Run with Docker Compose:

```bash
docker compose up --build
```

This brings up:
- `opcua-simulator` exposing OPC UA on `4840`
- `opcua2mcp_001` exposing MCP and HTTP on `5011`
- `opcua2mcp_002` exposing MCP and HTTP on `5021`
- `redis` for cache storage

## Environment variables

`app/app.py` supports the following environment variables:

- `MACHINE_NAME` — machine name from YAML config (`Machine-001`, `Machine-002`)
- `OPCUA_ENDPOINT` — OPC UA server URL
- `CACHE_BACKEND` — `memory` or `redis`
- `REDIS_URL` — Redis connection URL
- `CACHE_TTL` — seconds to keep cached sensor results
- `MCP_PORT` — internal HTTP/MCP service port
- `OPCUA_CONFIG` — path to the YAML config file

## API Reference

### MCP Exposure

`src/opcua2mcp.py` registers two MCP tools via `FastMCP`:

1. `health.check`
   - title: Machine Health Check
   - returns current machine health, score, alerts, and sensor readings

2. `read.sensors`
   - title: Read All Sensors
   - returns the latest sensor values for the configured machine

These tools are available through the MCP `/mcp` endpoint supported by `FastMCP`.

### HTTP Routes

In addition to the MCP tools, `opcua2mcp` exposes three HTTP endpoints on the same service port:

- `GET /health`
  - returns the current health status for the machine
  - fields include: `machine_name`, `status`, `health_score`, `alerts`, `total_sensors`, `sensor_readings`, `timestamp`

- `GET /sensors`
  - returns latest sensor values and status for every configured sensor
  - this forces a fresh read from OPC UA before replying

- `GET /cache`
  - returns the current cache contents
  - includes cached sensor readings stored in memory or Redis

### Example HTTP usage

```bash
curl http://localhost:5011/health
curl http://localhost:5011/sensors
curl http://localhost:5011/cache
```

## Why `opcua2mcp`?

This bridge is designed to sponsor MCP adoption by demonstrating a real IIoT use case:
- converting OPC UA telemetry into MCP tool semantics
- evaluating machine health automatically
- exposing both standard HTTP and MCP-compatible interfaces
- enabling multi-machine deployments with one YAML-driven config

## Extending the bridge

You can extend `src/opcua2mcp.py` by:
- adding new MCP tools for individual sensor reads
- enriching health logic with custom scoring rules
- adding additional OPC UA namespaces or node discovery
- supporting more machine types in `app/config.yaml`

## Important files

- `src/opcua2mcp.py` — main converter and MCP server definition
- `app/app.py` — launch script and environment-driven startup
- `app/opcua_simulator.py` — OPC UA simulator service
- `app/config.yaml` — sensor and simulator configuration
- `docker-compose.yml` — multi-service orchestration

## Notes

The MCP bridge uses `FastMCP` from the official `mcp` package, and the simulator uses `opcua` to host realistic sensor variables.

For development, run the stack locally and inspect the `/health`, `/sensors`, and `/cache` endpoints for immediate visibility into the OPC UA → MCP workflow.
