from fastapi import APIRouter, Request, HTTPException, WebSocket, Response
from fastapi.responses import StreamingResponse
import httpx
from httpx_ws import aconnect_ws
import asyncio
import logging
import time
from typing import Dict, Optional
from dataclasses import dataclass, field
from .services import app_service

# Set up logging
logger = logging.getLogger(__name__)

router = APIRouter()

@dataclass
class ConnectionStats:
    created_at: float = field(default_factory=time.time)
    last_activity: float = field(default_factory=time.time)
    messages_forwarded: int = 0
    reconnect_count: int = 0
    error_count: int = 0

class StreamlitWebSocketProxy:
    def __init__(self, max_retries=3):
        self.max_retries = max_retries
        self.connection_stats: Dict[str, ConnectionStats] = {}
        self.http_client = httpx.AsyncClient(
            timeout=httpx.Timeout(connect=10.0, read=30.0, write=10.0, pool=30.0),
            limits=httpx.Limits(
                max_connections=100,
                max_keepalive_connections=20,
                keepalive_expiry=30.0
            )
        )
    
    async def proxy_websocket(self, client_ws: WebSocket, target_url: str, slug: str, endpoint_name: str = ""):
        """Handle WebSocket proxying with comprehensive error handling and connection monitoring."""
        connection_id = f"{client_ws.client.host}:{client_ws.client.port}"
        stats = self.connection_stats[connection_id] = ConnectionStats()
        
        logger.info(f"{endpoint_name} WebSocket connection for slug '{slug}' -> {target_url}")
        
        try:
            await client_ws.accept(subprotocol="streamlit")
            logger.info(f"{endpoint_name} WebSocket accepted for slug '{slug}'")
        except Exception as e:
            logger.error(f"Failed to accept {endpoint_name} WebSocket for '{slug}': {e}")
            return

        retry_count = 0
        backoff = 1.0
        
        while retry_count < self.max_retries:
            try:
                await self._proxy_session(client_ws, target_url, slug, endpoint_name, stats)
                break  # Successful completion
                
            except httpx.ConnectError as e:
                retry_count += 1
                stats.reconnect_count += 1
                stats.error_count += 1
                
                if retry_count < self.max_retries:
                    wait_time = backoff * (2 ** retry_count)
                    logger.warning(f"Reconnecting in {wait_time}s after connection error: {e}")
                    await asyncio.sleep(wait_time)
                else:
                    logger.error(f"Max retries reached for {connection_id}")
                    await client_ws.close(code=1002, reason="Cannot connect to upstream")
                    break
                    
            except Exception as e:
                logger.error(f"Unexpected error for {connection_id}: {e}")
                stats.error_count += 1
                await client_ws.close(code=1011, reason=f"Proxy error: {str(e)}")
                break
        
        # Cleanup
        if connection_id in self.connection_stats:
            del self.connection_stats[connection_id]
    
    async def _proxy_session(self, client_ws: WebSocket, target_url: str, slug: str, endpoint_name: str, stats: ConnectionStats):
        """Single proxy session with health monitoring and proper header forwarding."""
        
        # Configure connection with aggressive keep-alive to compensate for Streamlit ping bug
        async with aconnect_ws(
            target_url,
            client=self.http_client,
            keepalive_ping_interval_seconds=15,  # Aggressive ping for Streamlit
            keepalive_ping_timeout_seconds=10,
            max_message_size_bytes=10*1024*1024  # 10MB for large Streamlit dataframes
        ) as backend_ws:
            
            logger.info(f"Connected to {endpoint_name} target WebSocket {target_url}")
            
            # Create forwarding tasks with optimized binary handling
            forward_task = asyncio.create_task(
                self._forward_client_to_backend(client_ws, backend_ws, slug)
            )
            backward_task = asyncio.create_task(
                self._forward_backend_to_client(backend_ws, client_ws, slug)
            )
            
            # Health check task to compensate for Streamlit ping bug
            health_task = asyncio.create_task(
                self._health_monitor(client_ws, backend_ws, stats)
            )
            
            # Wait for any task to complete
            done, pending = await asyncio.wait(
                [forward_task, backward_task, health_task],
                return_when=asyncio.FIRST_COMPLETED
            )
            
            # Cancel remaining tasks
            for task in pending:
                task.cancel()
                try:
                    await task
                except asyncio.CancelledError:
                    pass
    
    async def _forward_client_to_backend(self, client_ws, backend_ws, slug):
        """Forward messages from client to backend - always use binary for efficiency."""
        try:
            while True:
                try:
                    message = await client_ws.receive_bytes()
                    await backend_ws.send_bytes(message)
                    logger.debug(f"[{slug}] Client->Backend: {len(message)} bytes")
                except Exception as e:
                    logger.debug(f"[{slug}] Client disconnected: {e}")
                    break
                        
        except Exception as e:
            logger.error(f"[{slug}] Forward client->backend failed: {e}")

    async def _forward_backend_to_client(self, backend_ws, client_ws, slug):
        """Forward messages from backend to client - always use binary for efficiency."""
        try:
            while True:
                try:
                    # Receive with timeout to detect stale connections
                    message = await asyncio.wait_for(
                        backend_ws.receive(), 
                        timeout=60.0
                    )
                    
                    # Always extract bytes regardless of message type
                    if hasattr(message, 'data') and message.data is not None:
                        await client_ws.send_bytes(message.data)
                        logger.debug(f"[{slug}] Backend->Client: {len(message.data)} bytes")
                    elif hasattr(message, 'bytes') and message.bytes is not None:
                        await client_ws.send_bytes(message.bytes)
                        logger.debug(f"[{slug}] Backend->Client: {len(message.bytes)} bytes")
                    elif hasattr(message, 'text') and message.text is not None:
                        # Convert text to bytes for consistent binary forwarding
                        await client_ws.send_bytes(message.text.encode('utf-8'))
                        logger.debug(f"[{slug}] Backend->Client: {len(message.text)} chars (as bytes)")
                    else:
                        # Handle different message types from httpx_ws
                        if hasattr(message, 'type'):
                            # FastAPI WebSocket message
                            if message.type == "websocket.disconnect":
                                logger.info(f"[{slug}] Backend disconnected")
                                break
                            elif message.type == "websocket.receive":
                                if hasattr(message, 'text') and message.text is not None:
                                    await client_ws.send_bytes(message.text.encode('utf-8'))
                                    logger.debug(f"[{slug}] Backend->Client: {len(message.text)} chars (as bytes)")
                                elif hasattr(message, 'bytes') and message.bytes is not None:
                                    await client_ws.send_bytes(message.bytes)
                                    logger.debug(f"[{slug}] Backend->Client: {len(message.bytes)} bytes")
                        else:
                            # httpx_ws message (TextMessage, BytesMessage, etc.)
                            if hasattr(message, 'text'):
                                await client_ws.send_bytes(message.text.encode('utf-8'))
                                logger.debug(f"[{slug}] Backend->Client: {len(message.text)} chars (as bytes)")
                            elif hasattr(message, 'data'):
                                await client_ws.send_bytes(message.data)
                                logger.debug(f"[{slug}] Backend->Client: {len(message.data)} bytes")
                            
                except asyncio.TimeoutError:
                    # Send ping to check connection health
                    try:
                        if hasattr(backend_ws, 'ping'):
                            await backend_ws.ping()
                        logger.debug(f"[{slug}] Backend health check ping")
                    except Exception as e:
                        logger.warning(f"[{slug}] Backend health check failed: {e}")
                        raise
                    continue
                except RuntimeError as e:
                    # Handle the case where WebSocket is already disconnected
                    if "Cannot call \"receive\" once a disconnect message has been received" in str(e):
                        logger.info(f"[{slug}] Backend WebSocket already disconnected")
                        break
                    else:
                        logger.error(f"[{slug}] Backend RuntimeError: {e}")
                        raise
                    
        except Exception as e:
            logger.error(f"[{slug}] Forward backend->client failed: {e}")

    async def _forward_with_monitoring(self, source_ws, target_ws, direction: str, stats: ConnectionStats):
        """Legacy method - kept for compatibility but not used in new implementation."""
        pass
    
    async def _health_monitor(self, client_ws, backend_ws, stats):
        """Monitor connection health and send manual pings to compensate for Streamlit bug."""
        while True:
            await asyncio.sleep(20)  # Check every 20 seconds
            
            current_time = time.time()
            if current_time - stats.last_activity > 30:
                # No activity for 30 seconds, send manual ping
                try:
                    # Send ping to both sides
                    if hasattr(client_ws, 'ping'):
                        await client_ws.ping()
                    if hasattr(backend_ws, 'ping'):
                        pong = await backend_ws.ping()
                        await asyncio.wait_for(pong.wait(), timeout=5.0)
                    logger.debug("Health check: Sent manual pings")
                except Exception as e:
                    logger.warning(f"Health check failed: {e}")
                    raise httpx.ConnectError("Connection unhealthy")

# Global proxy instance
websocket_proxy = StreamlitWebSocketProxy()

async def cleanup_websocket_proxy():
    """Cleanup WebSocket proxy resources."""
    if websocket_proxy.http_client:
        await websocket_proxy.http_client.aclose()

@router.api_route("/{slug}/", methods=["GET", "POST", "PUT", "DELETE", "PATCH", "HEAD", "OPTIONS"])
async def proxy_app_root(slug: str, request: Request):
    """Proxy requests to the root of a Streamlit app."""
    logger.info(f"Proxying root request for slug '{slug}'")
    return await proxy_handler(slug, "", request)

@router.api_route("/{slug}/{path:path}", methods=["GET", "POST", "PUT", "DELETE", "PATCH", "HEAD", "OPTIONS"])
async def proxy_handler(slug: str, path: str, request: Request):
    """Proxy HTTP requests to the appropriate Streamlit app."""
    logger.info(f"Proxying request for slug '{slug}' path '{path}'")
    
    app = app_service.registry.find(slug)
    if not app:
        logger.error(f"App '{slug}' not found in registry")
        raise HTTPException(status_code=404, detail="App not found")

    # Auto-start the app if it's not running
    if not app_service.is_app_running(slug):
        logger.info(f"App '{slug}' not running, starting it")
        try:
            await app_service.start_app(slug)
            logger.info(f"App '{slug}' started")
        except Exception as e:
            logger.error(f"Failed to start app '{slug}': {str(e)}")
            raise HTTPException(status_code=500, detail=f"Failed to start app: {str(e)}")
    
    port = app_service.get_app_port(slug)
    logger.info(f"Forwarding request to port {port}")
    
    # Strip the slug prefix and forward to Streamlit as if it's at root
    target_url = f"http://127.0.0.1:{port}/{path}"
    
    # Forward query parameters
    if request.url.query:
        target_url += f"?{request.url.query}"
    
    logger.debug(f"Target URL: {target_url}")
    
    headers = dict(request.headers)
    # Remove problematic headers that might cause encoding issues
    headers.pop("host", None)
    headers.pop("accept-encoding", None)
    headers.pop("content-encoding", None)
    headers["host"] = f"127.0.0.1:{port}"
    
    client = await app_service.get_http_client()
    try:
        logger.debug(f"Making request to {target_url}")
        proxied = await client.request(
            method=request.method,
            url=target_url,
            content=await request.body(),
            headers=headers,
            cookies=request.cookies,
        )
        
        logger.debug(f"Received response with status {proxied.status_code}")
        
        # Filter response headers to avoid encoding issues
        response_headers = {}
        for key, value in proxied.headers.items():
            key_lower = key.lower()
            if key_lower not in [
                'content-length', 'transfer-encoding', 'connection',
                'content-encoding', 'accept-encoding'
            ]:
                response_headers[key] = value
        
        # Read the content as bytes to avoid encoding issues
        content = proxied.content
        
        return Response(
            content=content,
            status_code=proxied.status_code,
            headers=response_headers,
        )
    except httpx.ConnectError as e:
        logger.error(f"Connection error to {target_url}: {str(e)}")
        raise HTTPException(status_code=502, detail=f"Could not connect to app on port {port}")
    except httpx.TimeoutException as e:
        logger.error(f"Timeout error to {target_url}: {str(e)}")
        raise HTTPException(status_code=504, detail=f"Timeout connecting to app on port {port}")
    except httpx.RequestError as e:
        logger.error(f"Request error to {target_url}: {str(e)}")
        raise HTTPException(status_code=502, detail=f"Proxy error: {str(e)}")
    except Exception as e:
        logger.error(f"Unexpected error proxying to {target_url}: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Internal proxy error: {str(e)}")

# Create a global instance of the WebSocket proxy
websocket_proxy_instance = StreamlitWebSocketProxy()

async def websocket_proxy_with_httpx(websocket: WebSocket, target_url: str, slug: str, endpoint_name: str = ""):
    """Enhanced WebSocket proxy using the robust StreamlitWebSocketProxy."""
    await websocket_proxy_instance.proxy_websocket(websocket, target_url, slug, endpoint_name)

@router.websocket("/{slug}/stream")
async def websocket_proxy(websocket: WebSocket, slug: str):
    """Proxy WebSocket connections to the appropriate Streamlit app."""
    app = app_service.registry.find(slug)
    if not app:
        logger.error(f"App '{slug}' not found for WebSocket")
        await websocket.close(code=1008, reason="App not found")
        return

    # Auto-start the app if it's not running
    if not app_service.is_app_running(slug):
        logger.info(f"Starting app '{slug}' for WebSocket")
        try:
            await app_service.start_app(slug)
            # Wait for the app to fully start
            await asyncio.sleep(2)
            logger.info(f"App '{slug}' started for WebSocket")
        except Exception as e:
            logger.error(f"Failed to start app '{slug}' for WebSocket: {str(e)}")
            await websocket.close(code=1008, reason="Failed to start app")
            return
    
    port = app_service.get_app_port(slug)
    target_url = f"ws://127.0.0.1:{port}/stream"
    
    await websocket_proxy_with_httpx(websocket, target_url, slug, "Standard")

@router.websocket("/{slug}/_stcore/stream")
async def streamlit_websocket_proxy(websocket: WebSocket, slug: str):
    """Proxy Streamlit's core WebSocket connections with enhanced error handling."""
    logger.info(f"=== Streamlit WebSocket request for slug '{slug}' ===")
    
    app = app_service.registry.find(slug)
    if not app:
        logger.error(f"App '{slug}' not found for Streamlit WebSocket")
        await websocket.close(code=1008, reason="App not found")
        return

    # Auto-start the app if it's not running
    if not app_service.is_app_running(slug):
        logger.info(f"Starting app '{slug}' for Streamlit WebSocket")
        try:
            await app_service.start_app(slug)
            # Wait longer for Streamlit apps to fully initialize
            await asyncio.sleep(3)
            logger.info(f"App '{slug}' started for Streamlit WebSocket")
        except Exception as e:
            logger.error(f"Failed to start app '{slug}' for Streamlit WebSocket: {str(e)}")
            await websocket.close(code=1008, reason="Failed to start app")
            return

    port = app_service.get_app_port(slug)
    target_url = f"ws://127.0.0.1:{port}/_stcore/stream"
    logger.info(f"Target WebSocket URL: {target_url}")
    
    # Enhanced health check with retry logic
    health_check_passed = False
    for attempt in range(3):
        try:
            async with httpx.AsyncClient(timeout=5.0) as test_client:
                test_response = await test_client.get(f"http://127.0.0.1:{port}/healthz")
                if test_response.status_code == 200:
                    logger.info(f"Streamlit health check passed: {test_response.status_code}")
                    health_check_passed = True
                    break
                else:
                    logger.warning(f"Streamlit health check returned {test_response.status_code}")
        except Exception as e:
            logger.warning(f"Streamlit health check attempt {attempt + 1} failed: {e}")
            if attempt < 2:
                await asyncio.sleep(1)
    
    if not health_check_passed:
        logger.warning(f"Streamlit health check failed for '{slug}', but proceeding with WebSocket connection")
    
    await websocket_proxy_with_httpx(websocket, target_url, slug, "Streamlit")

@router.websocket("/{slug}/{ws_path:path}")
async def generic_websocket_proxy(websocket: WebSocket, slug: str, ws_path: str):
    """Proxy any WebSocket path to Streamlit."""
    # Skip non-WebSocket paths
    if not any(ws_indicator in ws_path.lower() for ws_indicator in ['stream', 'websocket', 'ws', '_stcore']):
        logger.warning(f"Rejecting non-WebSocket path '{ws_path}' for slug '{slug}'")
        await websocket.close(code=1002, reason="Not a WebSocket endpoint")
        return
    
    app = app_service.registry.find(slug)
    if not app:
        logger.error(f"App '{slug}' not found for generic WebSocket")
        await websocket.close(code=1008, reason="App not found")
        return

    # Auto-start the app if it's not running
    if not app_service.is_app_running(slug):
        logger.info(f"Starting app '{slug}' for generic WebSocket")
        try:
            await app_service.start_app(slug)
            await asyncio.sleep(2)
            logger.info(f"App '{slug}' started for generic WebSocket")
        except Exception as e:
            logger.error(f"Failed to start app '{slug}' for generic WebSocket: {str(e)}")
            await websocket.close(code=1008, reason="Failed to start app")
            return

    port = app_service.get_app_port(slug)
    target_url = f"ws://127.0.0.1:{port}/{ws_path}"
    
    await websocket_proxy_with_httpx(websocket, target_url, slug, f"Generic({ws_path})")