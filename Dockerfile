# IIoT Data Processor with Predictive Maintenance
# Docker container for edge deployment
# Based on research: Agentic AI + Industrial IoT + Predictive Maintenance
# Author: Giacomo Veneri

FROM python:3.12-slim


COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

EXPOSE 4840
EXPOSE 5001

# Health check
HEALTHCHECK --interval=30s --timeout=3s --start-period=5s --retries=3 \
    CMD python -c "import requests; requests.get('http://localhost:5001/health')" || exit 1

ENV PYTHONPATH "${PYTHONPATH}:/src:"

# Run application
CMD ["python", "app/app.py"]