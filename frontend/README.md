# Bike Log frontend

React 19 + TypeScript + Vite. All business logic is in the Python backend; this app only calls
`./api/...` (relative URLs) and displays the results.

```bash
npm ci
npm run build      # output: dist/, served by the backend at http://127.0.0.1:8765/
npm run lint
```

Development with hot reload: start the backend with `BIKELOG_DEV_TOKEN=dev` on port 8765, then
`npm run dev`; Vite proxies `/api` to the backend and sends the dev token from `.env` (`VITE_DEV_TOKEN=dev`).
In the built app the per-launch token is injected into `index.html` by the backend.
