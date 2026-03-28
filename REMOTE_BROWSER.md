# Remote Browser Mode

## Overview

This repository now contains the `remote_browser` integration needed to let a local Chrome session provide:

- up-to-date Session Token sync
- project-bound reCAPTCHA token acquisition
- local bridge APIs for `flow2api`
- VM helper scripts for the GCP deployment

The implementation is split into:

- `src/`
  Main `flow2api` service logic
- `tools/remote_browser_bridge/`
  Local bridge service
- `scripts/remote_browser/`
  Local bridge/tunnel/request scripts
- `scripts/vm/`
  VM helper scripts

The browser extension remains in the separate `Flow2API-Token-Updater` repository.

## Main Pieces

### 1. Main service

The main service accepts `project_id` on image/video requests and passes it through the generation path.

Key behaviors:

- request `project_id` takes priority over token `current_project_id`
- successful image responses include `generated_assets.media_id`
- the token manager uses a conservative AT refresh policy to avoid disabling otherwise usable tokens too early

### 2. Local bridge

The bridge lives under `tools/remote_browser_bridge/`.

It provides:

- `GET /health`
- `GET /api/v1/config`
- `GET /api/v1/debug/profile`
- `GET /api/v1/token-request`
- `POST /api/v1/plugin-sync-request`
- `POST /api/v1/plugin-sync-finish`
- `POST /api/v1/solve`
- `POST /api/v1/token-cache`
- `GET /api/v1/local/status`
- `POST /api/v1/local/boot`
- `POST /api/v1/local/request`

Important bridge behavior:

- caches tokens by `project_id + action`
- treats tokens as single-use on the bridge side
- records `recent_events` for debugging
- can now proxy local `Boot` and `Request` script entrypoints through HTTP

### 3. Local scripts

Use the scripts in `scripts/remote_browser/`.

#### Boot mode

Brings the local runtime into a healthy state:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\remote_browser\run_request.ps1 -Action Boot -TargetEmail kpveoiref@libertystreeteriepa.asia -ProjectId c6d7cff5-2977-4825-acbe-e978e4addc65
```

Boot does:

- verify/start local bridge
- verify/start reverse tunnel
- ensure VM host proxy path is healthy
- ensure `flow2api` uses `remote_browser`
- request extension ST sync
- open the target Flow project page
- ensure the target token is selected

#### Request mode

Uses the existing runtime and skips heavy repair:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\remote_browser\run_request.ps1 -Action Request -Mode image -TargetEmail kpveoiref@libertystreeteriepa.asia -ProjectId c6d7cff5-2977-4825-acbe-e978e4addc65
```

This is the recommended day-to-day mode after a successful boot.

#### Full mode

Runs full boot logic and then dispatches the request in one command:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\remote_browser\run_request.ps1 -Action Full -Mode image -TargetEmail kpveoiref@libertystreeteriepa.asia -ProjectId c6d7cff5-2977-4825-acbe-e978e4addc65
```

#### Matrix mode

Runs a request-mode smoke-test matrix after lightweight readiness checks.

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\remote_browser\run_request.ps1 -Action Matrix -TargetEmail kpveoiref@libertystreeteriepa.asia -ProjectId c6d7cff5-2977-4825-acbe-e978e4addc65
```

`Matrix` keeps the `Request` workflow shape:

- it does not run full heavy repair like `Boot`
- it does one light readiness check pass
- it syncs the extension token and opens the target project page once
- it then runs a sequential API matrix that covers:
  - text-to-image
  - image-to-image
  - text-to-video
  - image-to-video with one start frame
  - image-to-video with start/end frames
  - reference-to-video

## GCP VM helper scripts

VM scripts live in `scripts/vm/`.

Useful actions:

- `SetFlow2APIRemoteBrowserMode`
- `SelectFlow2APIToken`
- `RefreshFlow2APIToken`
- `InspectFlow2APITokenState`
- `SmokeTestFlow2API`
- `SmokeTestFlow2APIImg2Img`
- `SmokeTestFlow2APIVideo`

Example:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\vm\vm_manager.ps1 -Action InspectFlow2APITokenState -Zone us-central1-a
```

## API Usage

### Local control API

The local bridge now also acts as a small control-plane API for the local runtime.

These endpoints wrap the existing reusable script entrypoint:

- `scripts/remote_browser/run_request.ps1`

Use the same `Authorization: Bearer <bridge_api_key>` header as the other bridge APIs.

#### Local status

```http
GET /api/v1/local/status
```

Returns the local bridge runtime summary plus the resolved script locations.

#### Local boot

```http
POST /api/v1/local/boot
Content-Type: application/json

{
  "target_email": "kpveoiref@libertystreeteriepa.asia",
  "project_id": "c6d7cff5-2977-4825-acbe-e978e4addc65",
  "disable_other_tokens": true,
  "timeout_seconds": 300
}
```

This runs:

```powershell
.\scripts\remote_browser\run_request.ps1 -Action Boot ...
```

Use it to prepare the environment once at startup or after repair.

#### Local request

```http
POST /api/v1/local/request
Content-Type: application/json

{
  "mode": "image",
  "target_email": "kpveoiref@libertystreeteriepa.asia",
  "project_id": "c6d7cff5-2977-4825-acbe-e978e4addc65",
  "disable_other_tokens": true,
  "timeout_seconds": 600
}
```

This runs:

```powershell
.\scripts\remote_browser\run_request.ps1 -Action Request ...
```

Successful responses return:

- `success`
- `action`
- `command`
- `exit_code`
- `stdout`
- `stderr`

This is intended to be the stable local API wrapper for the current script-based workflow.

### Text-to-image

Send `project_id` at the top level:

```json
{
  "model": "gemini-3.1-flash-image-square",
  "project_id": "c6d7cff5-2977-4825-acbe-e978e4addc65",
  "messages": [
    {
      "role": "user",
      "content": "生成一张极简风格的蓝色圆形图标，白色背景。"
    }
  ],
  "stream": false
}
```

### Image-to-image

Use OpenAI-style multimodal content:

```json
{
  "model": "gemini-3.1-flash-image-square",
  "project_id": "c6d7cff5-2977-4825-acbe-e978e4addc65",
  "messages": [
    {
      "role": "user",
      "content": [
        {
          "type": "text",
          "text": "保留大树主体和整体构图，加入一只猫。"
        },
        {
          "type": "image_url",
          "image_url": {
            "url": "data:image/png;base64,..."
          }
        }
      ]
    }
  ],
  "stream": false
}
```

### Returned image metadata

Successful image responses can include:

- `generated_assets.origin_image_url`
- `generated_assets.final_image_url`
- `generated_assets.media_id`

`media_id` is the generated media resource id, not the Flow `edit_id`.

## Notes

- Keep a dedicated Flow project tab available in the browser for the requested `project_id`
- The extension should be reloaded after background/content-script changes
- The bridge stores runtime-only files under `tools/remote_browser_bridge/`; these are ignored by git
