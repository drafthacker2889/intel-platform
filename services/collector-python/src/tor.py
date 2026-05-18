"""
Tor circuit management: routing through Tor proxy and rotating circuits.
"""

import asyncio
import socket
from typing import Optional


class TorManager:
    """
    Manages Tor SOCKS proxy connection and circuit rotation via control port.
    """
    
    def __init__(self, socks_port: int = 9050, control_port: int = 9051, 
                 control_password: str = ""):
        self.socks_port = socks_port
        self.control_port = control_port
        self.control_password = control_password
        self._last_rotation = None
    
    async def get_new_circuit(self) -> bool:
        """Request a new Tor circuit via control port."""
        try:
            # Create socket to Tor control port
            reader, writer = await asyncio.open_connection("127.0.0.1", self.control_port)
            
            # Authenticate
            if self.control_password:
                writer.write(f'AUTHENTICATE "{self.control_password}"\r\n'.encode())
            else:
                writer.write(b'AUTHENTICATE ""\r\n')
            
            await writer.drain()
            response = await asyncio.wait_for(reader.readline(), timeout=5)
            
            if b"250" not in response:
                return False
            
            # Request new circuit
            writer.write(b"SIGNAL NEWNYM\r\n")
            await writer.drain()
            response = await asyncio.wait_for(reader.readline(), timeout=5)
            
            writer.close()
            await writer.wait_closed()
            
            return b"250" in response
        
        except Exception as e:
            print(f"Circuit rotation failed: {e}")
            return False
    
    async def get_exit_ip(self) -> Optional[str]:
        """Get current exit IP address (useful for debugging)."""
        try:
            reader, writer = await asyncio.open_connection(
                "127.0.0.1", self.socks_port, 
                sock=socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            )
            writer.close()
            # In real usage, you'd query an IP detection service through Tor
            return "Tor"
        except Exception:
            return None
