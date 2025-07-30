import asyncio
import logging
import socket
import time
from typing import Dict, Optional, Set
import subprocess
import httpx
from .models import AppConfig
from .app_registry import AppRegistry
from .config import STARTING_PORT, MAX_PORT

logger = logging.getLogger(__name__)

class AppService:
    def __init__(self):
        self.running: Dict[str, Dict] = {}
        self.used_ports: Set[int] = set()
        self.registry = AppRegistry()
        self._http_client: Optional[httpx.AsyncClient] = None

    async def get_http_client(self) -> httpx.AsyncClient:
        if self._http_client is None:
            self._http_client = httpx.AsyncClient(
                timeout=30.0,
                limits=httpx.Limits(max_keepalive_connections=20, max_connections=100)
            )
        return self._http_client

    async def close_http_client(self):
        if self._http_client:
            await self._http_client.aclose()
            self._http_client = None

    def _find_free_port(self) -> int:
        for port in range(STARTING_PORT, MAX_PORT):
            if port in self.used_ports:
                continue
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                if s.connect_ex(("127.0.0.1", port)) != 0:
                    return port
        raise Exception("No free ports available")

    def _is_port_in_use(self, port: int) -> bool:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            return s.connect_ex(("127.0.0.1", port)) == 0

    def _is_process_running(self, process) -> bool:
        if process is None:
            return False
        # Handle asyncio.Process objects
        if hasattr(process, 'returncode'):
            return process.returncode is None
        # Handle subprocess.Popen objects
        elif hasattr(process, 'poll'):
            return process.poll() is None
        return False

    def _cleanup_dead_processes(self):
        dead_slugs = []
        for slug, app_info in self.running.items():
            if not self._is_process_running(app_info['process']):
                dead_slugs.append(slug)
                self.used_ports.discard(app_info['port'])
        
        for slug in dead_slugs:
            del self.running[slug]

    def _update_last_access(self, slug: str):
        if slug in self.running:
            self.running[slug]['last_access'] = time.time()

    async def _wait_for_app_ready(self, port: int, max_wait: int = 30) -> bool:
        client = await self.get_http_client()
        
        for i in range(max_wait):
            try:
                response = await client.get(f"http://127.0.0.1:{port}/healthz")
                if response.status_code == 200:
                    logger.info(f"App on port {port} is ready")
                    return True
            except:
                pass
            
            try:
                response = await client.get(f"http://127.0.0.1:{port}/")
                if response.status_code == 200:
                    logger.info(f"App on port {port} is ready (via root)")
                    return True
            except:
                pass
                
            await asyncio.sleep(1)
        
        logger.warning(f"App on port {port} did not become ready within {max_wait} seconds")
        return False

    async def start_app(self, slug: str) -> int:
        logger.info(f"Starting app '{slug}'")
        
        self._cleanup_dead_processes()
        
        app = self.registry.find(slug)
        if not app:
            raise ValueError(f"App '{slug}' not found in registry")
        
        if slug in self.running:
            if self._is_process_running(self.running[slug]['process']):
                logger.info(f"App '{slug}' already running on port {self.running[slug]['port']}")
                return self.running[slug]['port']
            else:
                self.used_ports.discard(self.running[slug]['port'])
                del self.running[slug]
        
        port = app.desired_port or self._find_free_port()
        
        if self._is_port_in_use(port):
            port = self._find_free_port()
        
        try:
            logger.info(f"Starting new process for app '{slug}' on port {port}")
            
            process = await asyncio.create_subprocess_exec(
                "uv", "run", "streamlit", "run", app.path,
                "--server.port", str(port),
                "--server.enableCORS", "true",
                "--server.enableXsrfProtection", "false",
                "--server.enableWebsocketCompression", "false",
                "--server.allowRunOnSave", "false",
                "--server.headless", "true",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            
            self.running[slug] = {
                'process': process,
                'port': port,
                'last_access': time.time(),
                'external_process': False
            }
            self.used_ports.add(port)
            
            logger.info(f"Successfully started app '{slug}' on port {port} with PID {process.pid}")
            
            await asyncio.sleep(3)
            
            ready = await self._wait_for_app_ready(port)
            if not ready:
                logger.warning(f"App '{slug}' may not be fully ready")
            
            return port
            
        except Exception as e:
            logger.error(f"Failed to start app '{slug}': {str(e)}")
            if slug in self.running:
                del self.running[slug]
            self.used_ports.discard(port)
            raise

    def get_app_port(self, slug: str) -> Optional[int]:
        if slug in self.running:
            self._update_last_access(slug)
            return self.running[slug]['port']
        return None

    def is_app_running(self, slug: str) -> bool:
        if slug not in self.running:
            return False
        return self._is_process_running(self.running[slug]['process'])

    async def stop_app(self, slug: str):
        if slug not in self.running:
            return
        
        proc_info = self.running.pop(slug)
        process = proc_info['process']
        port = proc_info['port']
        
        try:
            process.terminate()
            try:
                await asyncio.wait_for(process.wait(), timeout=5)
            except asyncio.TimeoutError:
                process.kill()
                await process.wait()
            except asyncio.CancelledError:
                logger.debug(f"Process wait cancelled for app '{slug}'")
                raise
            
            self.used_ports.discard(port)
            logger.info(f"Stopped app '{slug}' on port {port}")
            
        except asyncio.CancelledError:
            logger.debug(f"Stop app cancelled for '{slug}'")
            raise
        except Exception as e:
            logger.error(f"Error stopping app '{slug}': {e}")
            self.running[slug] = proc_info

    async def cleanup_all(self):
        for slug in list(self.running.keys()):
            try:
                await self.stop_app(slug)
            except asyncio.CancelledError:
                logger.debug(f"Cleanup cancelled while stopping app '{slug}'")
                raise
            except Exception as e:
                logger.error(f"Error stopping app '{slug}' during cleanup: {e}")

# Global service instance
app_service = AppService() 