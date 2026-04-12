# Cloud Deployment

Deploy Olmec to the cloud so your group can test the digital twin and operator UI remotely.

## Fly.io (recommended)

### Prerequisites
```bash
# Install flyctl
brew install flyctl

# Login
fly auth login
```

### First deploy
```bash
# Launch the app (creates it on Fly.io)
fly launch --no-deploy

# Set the password (pick something your group knows)
fly secrets set OLMEC_PASSWORD=your-secret-password

# Deploy
fly deploy
```

### Subsequent deploys
```bash
fly deploy
```

### Access
Your app will be at `https://olmec.fly.dev` (or whatever name you chose).

- **Login:** `https://olmec.fly.dev/login`
- **Operator UI:** `https://olmec.fly.dev/operator/`
- **Digital Twin:** `https://olmec.fly.dev/olmec/`

Share the URL and password with your group. HTTPS is automatic (required for browser mic access).

### Update audio clips
Audio clips are baked into the Docker image. After generating new clips locally, redeploy:
```bash
fly deploy
```

### Logs
```bash
fly logs
```

### Cost
The `fly.toml` is configured with auto-stop — the machine shuts down when idle and boots on request (~3s cold start). With minimal usage, this stays within Fly.io's free tier.

## Railway (alternative)

1. Push your code to GitHub
2. Connect the repo to Railway
3. Set environment variables: `OLMEC_MODE=cloud`, `OLMEC_PASSWORD=...`, `OLMEC_VOICE=olmec-v1-fx`
4. Railway auto-detects the Dockerfile and deploys

## Environment Variables

| Variable | Required | Description |
|---|---|---|
| `OLMEC_MODE` | Yes | Set to `cloud` |
| `OLMEC_PASSWORD` | Yes | Shared password for access |
| `OLMEC_VOICE` | No | Voice directory name (default: `olmec-v1`) |
