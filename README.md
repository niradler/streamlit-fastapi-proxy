# Streamlit FastAPI Proxy

A FastAPI-based proxy server for managing and serving multiple Streamlit applications with full WebSocket support.

## Features

- 🚀 **Multiple Streamlit Apps**: Run and manage multiple Streamlit applications simultaneously
- 🔌 **WebSocket Support**: Full WebSocket proxying for real-time Streamlit features
- 📡 **HTTP Proxy**: Complete HTTP request/response proxying
- 🎛️ **App Management**: RESTful API for starting, stopping, and managing apps
- 📊 **App Registry**: Persistent storage of registered applications
- 🔄 **Auto Port Management**: Automatic port allocation and management
- 📝 **Access Tracking**: Track last access times for apps

## Installation

```bash
# Clone the repository
git clone <your-repo-url>
cd streamlit-fastapi-proxy

# Install dependencies with uv
uv sync

# Or install manually
pip install -e .
```

## Quick Start

1. **Start the proxy server:**
   ```bash
   uv run python main.py
   # Or use the CLI command
   uv run streamlit-proxy
   ```

2. **Register a Streamlit app:**
   ```bash
   curl -X POST "http://localhost:8000/apps/register" \
        -H "Content-Type: application/json" \
        -d '{
          "name": "Test App",
          "slug": "test-app", 
          "path": "/path/to/your/app.py"
        }'
   ```

3. **Start the app:**
   ```bash
   curl -X POST "http://localhost:8000/apps/test-app/start"
   ```

4. **Access your app:**
   Open `http://localhost:8000/apps/test-app/` in your browser

## API Endpoints

### App Management

- **GET** `/apps/` - List all registered apps with status
- **POST** `/apps/register` - Register a new Streamlit app
- **POST** `/apps/{slug}/start` - Start a specific app
- **POST** `/apps/{slug}/stop` - Stop a specific app  
- **GET** `/apps/{slug}/status` - Get detailed status of an app

### Proxy Endpoints

- **ALL** `/apps/{slug}/{path:path}` - Proxy HTTP requests to the app
- **WebSocket** `/apps/{slug}/stream` - Proxy WebSocket connections
- **WebSocket** `/apps/{slug}/_stcore/stream` - Proxy Streamlit core WebSocket

## Configuration

Environment variables:

- `APP_REGISTRY_PATH` - Path to app registry JSON file (default: `app_registry.json`)
- `STARTING_PORT` - Starting port for Streamlit apps (default: `8503`)
- `MAX_PORT` - Maximum port for Streamlit apps (default: `8550`)

## App Registration Format

```json
{
  "name": "My Streamlit App",
  "slug": "my-app",
  "path": "/absolute/path/to/app.py",
  "desired_port": 8503,
  "run_by_default": false
}
```

## WebSocket Support

This proxy provides full WebSocket support for Streamlit's real-time features:

- ✅ Real-time widget updates
- ✅ Interactive plots and charts  
- ✅ Live data streaming
- ✅ Session state synchronization
- ✅ Auto-rerun functionality

## Example Usage

See the `apps/test_app.py` for a sample Streamlit application that demonstrates WebSocket functionality.

## Development

```bash
# Run in development mode with auto-reload
uv run uvicorn streamlit_proxy.main:create_app --reload --host 0.0.0.0 --port 8000

# Run tests (if available)
uv run pytest

# Format code
uv run black .
uv run isort .
```

## Architecture

```
┌─────────────────┐    HTTP/WS     ┌─────────────────┐
│   Client        │ ◄─────────────► │  FastAPI Proxy  │
│   Browser       │                │  (Port 8000)    │
└─────────────────┘                └─────────────────┘
                                           │
                                           │ HTTP/WS Proxy
                                           ▼
                                   ┌─────────────────┐
                                   │  Streamlit Apps │
                                   │  (Ports 8503+)  │
                                   │                 │
                                   │  ┌──────────┐   │
                                   │  │ App 1    │   │
                                   │  │ App 2    │   │
                                   │  │ App N... │   │
                                   │  └──────────┘   │
                                   └─────────────────┘
```

## License

[Add your license here]