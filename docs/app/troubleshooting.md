# Troubleshooting

Common issues and solutions.

---

### `zsh: command not found: docker`

Docker is not installed. Install Docker Desktop or use Homebrew MySQL as an alternative.

### SDK / Expo Go version mismatch

Check `frontend/package.json`:

```json
"expo": "~55.0.0",
"react": "19.2.0",
"react-native": "0.83.2"
```

Reinstall if needed:

```bash
rm -rf node_modules package-lock.json
npm install --legacy-peer-deps
```

### React Native codegen error (`RCTModalHostViewNativeComponent`)

React Native version is too new. Install the correct version:

```bash
npm install react-native@0.83.2 --legacy-peer-deps
```

### Port 8081 already in use

Kill the old process:

```bash
kill $(lsof -t -i :8081)
```

### `failed to load items`

Check:

1. Backend is running: `curl http://localhost:8000/api/health`
2. MySQL is running
3. If on real device, use your Mac IP instead of `localhost`
4. The app sends the API token (a `401` response means the token is missing or wrong)

### `401 Missing or invalid API token`

The request did not carry `Authorization: Bearer <API_TOKEN>`, or the token does not match `.env`. See [Setup §3.7](setup.md#37-api-authentication).

### `422 Unprocessable Entity`

The request body failed validation, for example a date that is not `YYYY-MM-DD`
(or does not exist, such as `2026-02-30`), or `null` sent for a required field.
The response `detail` is a list; each entry names the field (`loc`) and the reason (`msg`).

### Backend fails to start: `API_TOKEN is not set`

Set `API_TOKEN` in `.env` (see [Setup §3.7](setup.md#37-api-authentication)), or set `API_AUTH_DISABLED=true` for local development only.

### Connection refused

Backend not running. Start it with uvicorn.

### Python module not found

```bash
source .venv/bin/activate
pip install -e .
```

### Frontend module not found

```bash
rm -rf node_modules package-lock.json
npm install --legacy-peer-deps
```

### TypeScript errors

```bash
cd frontend
npx tsc --noEmit
```

### Expo shows old code

Clear cache:

```bash
npx expo start -c
```
