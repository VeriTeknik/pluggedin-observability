# Production Server Setup for Pluggedin-App Observability

This guide provides step-by-step instructions for setting up log shipping and metrics scraping from the pluggedin-app production server to monitoring.plugged.in.

## Prerequisites

- Root or sudo access on pluggedin-app production server (plugged.in)
- SSH access to monitoring server (monitoring.plugged.in / 185.96.168.253)
- Network connectivity between servers
- Current setup: pluggedin-app running as systemd service on port 12005

## Architecture Overview

```
[pluggedin-app Server: plugged.in]
    ↓ (logs)                    ↓ (metrics)
    ↓ Promtail → Loki           ↓ Prometheus scrapes /api/metrics
    ↓                           ↓
[Monitoring Server: monitoring.plugged.in / 185.96.168.253]
    ↓
[Grafana Dashboards & Alerts]
```

---

## Part 1: Install Promtail on Pluggedin-App Server

### 1.1 Download and Install Promtail

```bash
# SSH to pluggedin-app production server
ssh pluggedin@plugged.in

# Create directory for Promtail
sudo mkdir -p /opt/promtail
cd /opt/promtail

# Download Promtail v2.9.3 (same version as monitoring server)
sudo wget https://github.com/grafana/loki/releases/download/v2.9.3/promtail-linux-amd64.zip

# Unzip
sudo unzip promtail-linux-amd64.zip

# Make executable
sudo chmod +x promtail-linux-amd64

# Create symlink for easier access
sudo ln -sf /opt/promtail/promtail-linux-amd64 /usr/local/bin/promtail

# Verify installation
promtail --version
# Expected: promtail, version 2.9.3
```

### 1.2 Create Promtail Configuration Directory

```bash
# Create config directory
sudo mkdir -p /etc/promtail

# Create positions directory (for tracking what's been read)
sudo mkdir -p /var/lib/promtail

# Set ownership
sudo chown -R pluggedin:pluggedin /var/lib/promtail
```

### 1.3 Create Promtail Configuration File

**IMPORTANT**: Replace `MONITORING_SERVER_IP` with the actual internal IP of monitoring.plugged.in

```bash
sudo nano /etc/promtail/promtail-config.yml
```

Paste the following configuration:

```yaml
server:
  http_listen_port: 9080
  grpc_listen_port: 0
  log_level: info

positions:
  filename: /var/lib/promtail/positions.yaml

clients:
  - url: http://MONITORING_SERVER_IP:3100/loki/api/v1/push
    # If monitoring server requires authentication, add:
    # basic_auth:
    #   username: promtail
    #   password: <your-password>

    # Batching configuration for near real-time shipping (1-5 sec)
    batchwait: 2s
    batchsize: 102400

    # Retry configuration
    backoff_config:
      min_period: 500ms
      max_period: 5m
      max_retries: 10

    # Timeout
    timeout: 10s

scrape_configs:
  # Main application logs from systemd service
  - job_name: pluggedin-app
    static_configs:
      - targets:
          - localhost
        labels:
          job: pluggedin-app
          service: pluggedin-app
          environment: production
          host: plugged.in
          __path__: /var/log/pluggedin/pluggedin_app.log

    # Parse JSON logs
    pipeline_stages:
      # Read entire line
      - json:
          expressions:
            level: level
            msg: msg
            time: time
            trace_id: trace_id
            request_id: request_id
            event: event
            userId: userId
            serverUuid: serverUuid
            duration_ms: duration_ms
            service_name: service
            version: version
            severity: severity
            error: err
            req: req
            res: res
            statusCode: statusCode
            method: method
            url: url
            ip: ip

      # Extract timestamp
      - timestamp:
          source: time
          format: RFC3339

      # Add labels from extracted fields
      - labels:
          level:
          trace_id:
          event:
          service_name:

      # Replace level label if it's numeric (Pino levels)
      - template:
          source: level
          template: '{{ if eq .level "10" }}trace{{ else if eq .level "20" }}debug{{ else if eq .level "30" }}info{{ else if eq .level "40" }}warn{{ else if eq .level "50" }}error{{ else if eq .level "60" }}fatal{{ else }}{{ .level }}{{ end }}'

      - labels:
          level:

      # Output only relevant log line
      - output:
          source: msg

  # System auth logs (for security monitoring)
  - job_name: system-auth
    static_configs:
      - targets:
          - localhost
        labels:
          job: system-auth
          service: pluggedin-app-system
          environment: production
          host: plugged.in
          __path__: /var/log/auth.log

    pipeline_stages:
      - match:
          selector: '{job="system-auth"}'
          stages:
            - regex:
                expression: '^(?P<timestamp>\w+\s+\d+\s+\d+:\d+:\d+)\s+(?P<hostname>\S+)\s+(?P<process>\S+?)(\[(?P<pid>\d+)\])?: (?P<message>.*)$'
            - timestamp:
                source: timestamp
                format: "Jan 02 15:04:05"
            - labels:
                process:

  # Nginx/reverse proxy logs (if applicable)
  - job_name: nginx-access
    static_configs:
      - targets:
          - localhost
        labels:
          job: nginx-access
          service: pluggedin-app-proxy
          environment: production
          host: plugged.in
          __path__: /var/log/nginx/access.log

    pipeline_stages:
      - regex:
          expression: '^(?P<remote_addr>[\w\.]+) - (?P<remote_user>[^ ]*) \[(?P<time_local>.*?)\] "(?P<method>\S+)(?: +(?P<path>\S+) +\S*)?" (?P<status>\d+) (?P<body_bytes_sent>\d+) "(?P<http_referer>[^"]*)" "(?P<http_user_agent>[^"]*)"'
      - labels:
          method:
          status:
      - timestamp:
          source: time_local
          format: "02/Jan/2006:15:04:05 -0700"
```

**Configuration Notes**:
- Replace `MONITORING_SERVER_IP` with actual monitoring server IP (e.g., `185.96.168.253` or internal IP)
- If servers are on same host/Docker network, use `loki` as hostname
- Adjust `batchwait` (currently 2s) for shipping frequency
- The pipeline parses JSON logs from Pino logger and extracts relevant fields

### 1.4 Set Correct Permissions

```bash
# Set ownership
sudo chown -R pluggedin:pluggedin /etc/promtail

# Ensure promtail can read log files
sudo usermod -a -G adm pluggedin  # Add to adm group for /var/log access
sudo chmod 640 /var/log/pluggedin/pluggedin_app.log
sudo chown pluggedin:pluggedin /var/log/pluggedin/pluggedin_app.log
```

---

## Part 2: Create Promtail Systemd Service

### 2.1 Create Service File

```bash
sudo nano /etc/systemd/system/promtail.service
```

Paste the following:

```ini
[Unit]
Description=Promtail Log Shipper for Plugged.in
Documentation=https://grafana.com/docs/loki/latest/clients/promtail/
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
User=pluggedin
Group=pluggedin
ExecStart=/usr/local/bin/promtail -config.file=/etc/promtail/promtail-config.yml
Restart=always
RestartSec=10
StartLimitInterval=60
StartLimitBurst=3

# Logging
StandardOutput=journal
StandardError=journal
SyslogIdentifier=promtail

# Security hardening
NoNewPrivileges=true
ProtectSystem=strict
ProtectHome=true
ReadWritePaths=/var/lib/promtail
ReadOnlyPaths=/var/log/pluggedin /var/log/auth.log /var/log/nginx

# Resource limits
LimitNOFILE=8192
MemoryLimit=256M

[Install]
WantedBy=multi-user.target
```

### 2.2 Enable and Start Promtail

```bash
# Reload systemd
sudo systemctl daemon-reload

# Enable service (start on boot)
sudo systemctl enable promtail

# Start service
sudo systemctl start promtail

# Check status
sudo systemctl status promtail

# View logs
sudo journalctl -u promtail -f
```

**Expected output**: Service should be active (running) with no errors. You should see log lines indicating successful connection to Loki.

### 2.3 Verify Promtail is Shipping Logs

```bash
# Check Promtail metrics endpoint (should show processed logs)
curl http://localhost:9080/metrics | grep promtail_

# Check positions file (should update as logs are read)
cat /var/lib/promtail/positions.yaml

# Test connectivity to Loki on monitoring server
curl -I http://MONITORING_SERVER_IP:3100/ready
# Should return: HTTP/1.1 200 OK
```

---

## Part 3: Configure Log Rotation

### 3.1 Create Logrotate Configuration

```bash
sudo nano /etc/logrotate.d/pluggedin-app
```

Paste the following:

```
/var/log/pluggedin/pluggedin_app.log {
    daily
    rotate 14
    compress
    delaycompress
    missingok
    notifempty
    create 0640 pluggedin pluggedin
    sharedscripts
    postrotate
        # Signal Promtail to reopen log files
        systemctl reload promtail > /dev/null 2>&1 || true

        # Restart pluggedin app to reopen log file
        systemctl restart pluggedin > /dev/null 2>&1 || true
    endscript
}
```

### 3.2 Test Logrotate

```bash
# Test configuration
sudo logrotate -d /etc/logrotate.d/pluggedin-app

# Force rotation (optional, for testing)
sudo logrotate -f /etc/logrotate.d/pluggedin-app

# Verify rotated logs
ls -lh /var/log/pluggedin/
```

---

## Part 4: Network & Firewall Configuration

### 4.1 Check Current Network Connectivity

```bash
# From pluggedin-app server, test Loki connectivity
curl -I http://MONITORING_SERVER_IP:3100/ready

# Test Prometheus connectivity (if monitoring scrapes from external IP)
curl http://localhost:12005/api/metrics
```

### 4.2 Configure Firewall (if needed)

**On Monitoring Server** (185.96.168.253):
```bash
# Allow Loki push from pluggedin-app server
sudo ufw allow from <PLUGGEDIN_APP_SERVER_IP> to any port 3100 proto tcp comment 'Loki from pluggedin-app'

# Verify rule
sudo ufw status numbered
```

**On Pluggedin-App Server** (plugged.in):
```bash
# Allow Prometheus scraping from monitoring server (if not already allowed)
sudo ufw allow from 185.96.168.253 to any port 12005 proto tcp comment 'Prometheus metrics scraping'

# Verify rule
sudo ufw status numbered
```

### 4.3 Verify Metrics Endpoint Access

```bash
# From monitoring server, test metrics endpoint
ssh user@185.96.168.253
curl -I http://<PLUGGEDIN_APP_SERVER_IP>:12005/api/metrics

# Should return: HTTP/1.1 200 OK
# If 403 Forbidden, check METRICS_ALLOWED_IPS environment variable
```

---

## Part 5: Testing & Validation

### 5.1 Generate Test Logs

**On pluggedin-app server**:
```bash
# Restart app to generate startup logs
sudo systemctl restart pluggedin

# Watch logs being written
tail -f /var/log/pluggedin/pluggedin_app.log

# Check Promtail is reading them
sudo journalctl -u promtail -f

# Verify Promtail metrics
curl http://localhost:9080/metrics | grep -E 'promtail_read_bytes_total|promtail_sent_bytes_total'
```

### 5.2 Verify in Grafana

**On monitoring server or via web browser**:
1. Navigate to https://monitoring.plugged.in
2. Login to Grafana
3. Go to **Explore**
4. Select **Loki** data source
5. Query: `{service="pluggedin-app"}`
6. You should see recent logs from pluggedin-app

**Useful Loki queries**:
```logql
# All pluggedin-app logs
{service="pluggedin-app"}

# Error logs only
{service="pluggedin-app"} |= "error" or {service="pluggedin-app", level="error"}

# Logs with trace_id
{service="pluggedin-app"} | json | trace_id != ""

# High latency requests
{service="pluggedin-app"} | json | duration_ms > 1000

# Authentication events
{service="pluggedin-app", event="auth"}
```

### 5.3 Verify Metrics in Prometheus

**On monitoring server or via web browser**:
1. Navigate to https://monitoring.plugged.in/prometheus
2. Go to **Status > Targets**
3. Find `pluggedin-app` job
4. Status should be **UP** (green)
5. Last scrape should be recent (< 30 seconds ago)

**Test Prometheus queries**:
```promql
# Request rate
rate(http_requests_total{service="pluggedin-app"}[5m])

# Error rate
rate(http_requests_total{service="pluggedin-app", status=~"5.."}[5m])

# 95th percentile latency
histogram_quantile(0.95, rate(http_request_duration_seconds_bucket{service="pluggedin-app"}[5m]))

# MCP OAuth flows
rate(mcp_oauth_flows_total[5m])

# Active MCP sessions
mcp_sessions_active
```

---

## Part 6: Troubleshooting

### Issue: Promtail Not Starting

```bash
# Check service status
sudo systemctl status promtail

# View detailed logs
sudo journalctl -u promtail -n 100 --no-pager

# Common causes:
# 1. Config file syntax error - validate YAML
# 2. Permission denied - check file permissions
# 3. Port already in use - check if 9080 is available
netstat -tuln | grep 9080
```

### Issue: Logs Not Appearing in Loki

```bash
# Check Promtail is reading logs
cat /var/lib/promtail/positions.yaml
# Should show current position in log file

# Check Promtail metrics
curl http://localhost:9080/metrics | grep promtail_read_bytes_total
# Should be increasing

# Test Loki connectivity
curl -v http://MONITORING_SERVER_IP:3100/ready

# Check firewall
sudo ufw status | grep 3100

# Check Loki logs on monitoring server
docker-compose logs -f loki
```

### Issue: Metrics Endpoint Returns 403 Forbidden

```bash
# Check environment variable
grep METRICS_ALLOWED_IPS /home/pluggedin/pluggedin-app/.env

# Verify monitoring server IP is included
# Should contain: 185.96.168.253/32

# Restart app after updating .env
sudo systemctl restart pluggedin

# Test from monitoring server
curl -v http://<PLUGGEDIN_APP_IP>:12005/api/metrics
```

### Issue: Prometheus Can't Scrape Metrics

```bash
# Check Prometheus targets page
# Go to: https://monitoring.plugged.in/prometheus/targets

# Check scrape config on monitoring server
cat /path/to/prometheus/prometheus.yml | grep -A 10 pluggedin-app

# Test direct connectivity from monitoring server
ssh user@monitoring-server
curl -I http://<PLUGGEDIN_APP_IP>:12005/api/metrics

# Check network/firewall
sudo ufw status | grep 12005
```

### Issue: High Promtail Memory Usage

```bash
# Check current memory usage
systemctl status promtail

# Reduce batch size in config
sudo nano /etc/promtail/promtail-config.yml
# Change: batchsize: 51200 (from 102400)

# Restart Promtail
sudo systemctl restart promtail
```

---

## Part 7: Monitoring the Monitoring

### Set Up Alerts for Promtail Health

On monitoring server, add to Prometheus alerts:

```yaml
- alert: PromtailDown
  expr: up{job="promtail"} == 0
  for: 5m
  labels:
    severity: critical
  annotations:
    summary: "Promtail is down on {{ $labels.instance }}"
    description: "Promtail log shipper has been down for more than 5 minutes"

- alert: PromtailHighErrorRate
  expr: rate(promtail_file_errors_total[5m]) > 0.1
  for: 5m
  labels:
    severity: warning
  annotations:
    summary: "Promtail experiencing high error rate"
    description: "Promtail error rate is {{ $value }} errors/sec"
```

### Create Grafana Dashboard for Promtail

Monitor Promtail itself:
- Bytes read per second
- Bytes sent to Loki
- Error rate
- Active targets
- Lag time (current time vs log timestamp)

---

## Part 8: Rollback Plan

If issues arise, you can safely disable log shipping:

```bash
# Stop Promtail
sudo systemctl stop promtail

# Disable auto-start
sudo systemctl disable promtail

# The app will continue running normally
# Logs will still be written to /var/log/pluggedin/pluggedin_app.log
```

To re-enable:
```bash
sudo systemctl enable promtail
sudo systemctl start promtail
```

---

## Part 9: Maintenance Tasks

### Weekly
- Check Grafana for log gaps or missing metrics
- Review alert notifications
- Verify disk space on both servers

### Monthly
- Review log retention policies
- Check Promtail version for updates
- Audit alert rules for false positives/negatives

### Quarterly
- Test disaster recovery (restore from backups)
- Review and optimize Loki queries
- Update documentation

---

## Summary Checklist

- [ ] Promtail installed on pluggedin-app server
- [ ] Promtail configuration file created with correct Loki URL
- [ ] Promtail systemd service created and enabled
- [ ] Promtail service running without errors
- [ ] Log rotation configured
- [ ] Firewall rules configured (if needed)
- [ ] Logs visible in Grafana/Loki
- [ ] Prometheus scraping metrics successfully
- [ ] Metrics visible in Prometheus
- [ ] Alerts configured and tested
- [ ] Grafana dashboard created
- [ ] Documentation updated
- [ ] Rollback plan tested

---

## Support & Resources

- **Grafana Loki Docs**: https://grafana.com/docs/loki/latest/
- **Promtail Docs**: https://grafana.com/docs/loki/latest/clients/promtail/
- **Prometheus Docs**: https://prometheus.io/docs/
- **Internal Docs**: See `/Users/ckaraca/Mns/pluggedin-observability/README.md`

---

## Contact

For issues or questions during implementation:
- Check troubleshooting section above
- Review logs: `sudo journalctl -u promtail -f`
- Test connectivity between servers
- Verify configuration files for syntax errors
