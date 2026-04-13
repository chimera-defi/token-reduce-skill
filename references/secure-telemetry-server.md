# Secure Telemetry Server (Local)

## Status

Configured and validated on this host.

- Service: `token-reduce-telemetry.service`
- Bind: `127.0.0.1:18787` (loopback only)
- Ingest path: `/ingest`
- Health: `/healthz`
- Upload check: `telemetry-sync` returned `uploaded (http 200)`

## Security Controls Applied

- Loopback-only listener (`127.0.0.1`) to prevent public exposure
- API key validation (`x-token-reduce-key`)
- HMAC signature validation (`x-token-reduce-signature`)
- Secrets stored in root-only env file:
  - `/etc/token-reduce-telemetry.env` (`chmod 600`)
- Telemetry client config file permission tightened:
  - `/root/.config/token-reduce/config.json` (`chmod 600`)
- systemd hardening:
  - `NoNewPrivileges=true`
  - `ProtectSystem=strict`
  - `ProtectHome=read-only`
  - `PrivateTmp=true`
  - `RestrictAddressFamilies=AF_INET AF_INET6 AF_UNIX`
  - `IPAddressDeny=any` with allowlist `127.0.0.1` and `::1`

## Runtime Paths

- Unit file: `/etc/systemd/system/token-reduce-telemetry.service`
- Receiver output: `/var/lib/token-reduce-telemetry/ingest.jsonl`
- uv cache for service: `/var/lib/token-reduce-telemetry/uv-cache`

## Verify

```bash
systemctl status token-reduce-telemetry.service
ss -ltnp | rg 18787
curl -sS http://127.0.0.1:18787/healthz
tail -n 1 /var/lib/token-reduce-telemetry/ingest.jsonl
```

Expected:
- listener on `127.0.0.1:18787` only
- health returns `{"ok": true}`

## Rotate Secrets

```bash
API_KEY="$(openssl rand -hex 24)"
SIGNING_SECRET="$(openssl rand -hex 48)"
cat > /etc/token-reduce-telemetry.env <<EOF
API_KEY=$API_KEY
SIGNING_SECRET=$SIGNING_SECRET
EOF
chmod 600 /etc/token-reduce-telemetry.env
systemctl restart token-reduce-telemetry.service

./scripts/token-reduce-manage.sh settings set telemetry.api_key "$API_KEY"
./scripts/token-reduce-manage.sh settings set telemetry.signing_secret "$SIGNING_SECRET"
chmod 600 /root/.config/token-reduce/config.json
```

## Stop / Disable

```bash
systemctl disable --now token-reduce-telemetry.service
```

Optional cleanup:

```bash
rm -f /etc/systemd/system/token-reduce-telemetry.service
systemctl daemon-reload
```
