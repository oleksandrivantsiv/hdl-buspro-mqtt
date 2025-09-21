import asyncio
import threading
import logging
import hdl_component


logger = logging.getLogger(__name__)


class HDLListener(asyncio.DatagramProtocol):

    def __init__(self, host, port, components_ctl):
        self.transport = None
        self.host = host
        self.port = port
        self.components_ctl = components_ctl
        self.hdl_host = self.components_ctl.get_hdl_host()

    def connection_made(self, transport):
        self.transport = transport

    def datagram_received(self, data, addr):
        try:
            ip, _ = addr
            if ip != self.hdl_host:
                self.components_ctl.update_hdl_host(ip)
                self.hdl_host = ip

            self.components_ctl.update(data)
        except hdl_component.HDLValidationError as e:
            logger.error(f"Update error: {e}")
        except Exception as e:
            logger.error(f"Unhandled exception: {e}")

    def worker(self):
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        logger.debug("Starting UDP server")

        def protocol_factory():
            return self

        listen = loop.create_datagram_endpoint(protocol_factory, local_addr=(self.host, self.port))
        transport, protocol = loop.run_until_complete(listen)

        try:
            loop.run_forever()
        except KeyboardInterrupt:
            pass

        transport.close()

    def run(self):
        thread = threading.Thread(target=self.worker)
        thread.start()
        return thread

