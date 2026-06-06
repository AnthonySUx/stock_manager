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
