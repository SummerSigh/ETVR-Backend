from __future__ import annotations
from .config import EyeTrackConfig, OSCConfig
from .logger import get_logger
from .types import EyeData, EyeID
import threading
from multiprocessing import Process
from queue import Queue
from pythonosc.dispatcher import Dispatcher
from pythonosc.udp_client import SimpleUDPClient
from pythonosc.osc_server import ThreadingOSCUDPServer


logger = get_logger()


class VRChatOSC:
    def __init__(self, config: EyeTrackConfig, osc_queue: Queue[EyeData]):
        self.osc_queue: Queue[EyeData] = osc_queue
        self.main_config: EyeTrackConfig = config
        self.config: OSCConfig = config.osc
        self.client = SimpleUDPClient(self.config.address, self.config.sending_port)
        self.process: Process = Process()

    def __del__(self):
        if self.process.is_alive():
            self.stop()

    def is_alive(self) -> bool:
        return self.process.is_alive()

    def start(self) -> None:
        # don't start a thread if one already exists
        if self.process.is_alive():
            logger.debug(f"Process `{self.process.name}` requested to start but is already running")
            return

        logger.info("Starting OSC process")
        logger.info(f"OSC Sender serving on {self.config.address}:{self.config.sending_port}")
        # We might need to recreate the client because it may or may not be able to use new settings, will need to test
        # self.client = SimpleUDPClient(self.config.address, self.config.sending_port)
        self.process = Process(target=self._run, name="OSC")
        self.process.daemon = True
        self.process.start()

    def stop(self) -> None:
        # can't kill a non-existent thread
        if not self.process.is_alive():
            logger.debug("Request to kill dead process was made!")
            return

        logger.info("Stopping OSC process")
        self.process.kill()

    def restart(self) -> None:
        self.stop()
        self.start()

    def _run(self) -> None:
        while True:
            try:
                eye_data: EyeData = self.osc_queue.get(block=True, timeout=0.1)
            except Exception:
                continue

            if self.config.mirror_eyes:
                self.client.send_message(self.config.osc_endpoints.eyes_y, eye_data.y)
                self.client.send_message(self.config.osc_endpoints.left_eye_x, eye_data.x)
                self.client.send_message(self.config.osc_endpoints.right_eye_x, eye_data.x)
                self.client.send_message(self.config.osc_endpoints.left_eyelid_squeeze, eye_data.blink)
                self.client.send_message(self.config.osc_endpoints.right_eyelid_squeeze, eye_data.blink)
                return

            if eye_data.eye_id == EyeID.LEFT:
                self.client.send_message(self.config.osc_endpoints.eyes_y, eye_data.y)
                self.client.send_message(self.config.osc_endpoints.left_eye_x, eye_data.x)
                self.client.send_message(self.config.osc_endpoints.left_eyelid_squeeze, eye_data.blink)
            elif eye_data.eye_id == EyeID.RIGHT:
                self.client.send_message(self.config.osc_endpoints.eyes_y, eye_data.y)
                self.client.send_message(self.config.osc_endpoints.right_eye_x, eye_data.x)
                self.client.send_message(self.config.osc_endpoints.right_eyelid_squeeze, eye_data.blink)


# TODO: refactor this
class VRChatOSCReceiver:
    def __init__(self, config: EyeTrackConfig):
        self.main_config: EyeTrackConfig = config
        self.config: OSCConfig = config.osc
        self.dispatcher: Dispatcher = Dispatcher()
        self.server: ThreadingOSCUDPServer = ThreadingOSCUDPServer((self.config.address, self.config.receiver_port), self.dispatcher)
        self.thread: threading.Thread = threading.Thread()

    def __del__(self):
        if self.thread.is_alive():
            self.stop()

    def is_alive(self) -> bool:
        return self.thread.is_alive()

    def recalibrate_eyes(self, address, osc_value) -> None:
        pass

    def recenter_eyes(self, address, osc_value) -> None:
        pass

    def toggle_sync_blink(self, address, osc_value) -> None:
        self.config.sync_blink = not self.config.sync_blink

    def map_events(self) -> None:
        self.dispatcher.map(self.config.recalibrate_address, self.recalibrate_eyes)
        self.dispatcher.map(self.config.recenter_address, self.recenter_eyes)
        self.dispatcher.map(self.config.sync_blink_address, self.toggle_sync_blink)

    def start(self) -> None:
        # don't start a thread if one already exists
        if self.thread.is_alive():
            logger.debug(f"Thread `{self.thread.name}` requested to start but is already running")
            return

        logger.info("Starting OSC receiver thread")
        # we redefine the OSC server here just incase the address or port changed
        self.server.socket.close()  # close the old socket so we don't get a "address already in use" error
        self.server = ThreadingOSCUDPServer((self.config.address, self.config.receiver_port), self.dispatcher)
        logger.info(f"OSC receiver listening on {self.config.address}:{self.config.receiver_port}")
        self.map_events()
        self.thread = threading.Thread(target=self.server.serve_forever, name="OSC Receiver")
        self.thread.start()

    def stop(self) -> None:
        if not self.thread.is_alive():
            logger.debug("Request to kill dead thread was made!")
            return

        logger.info("Stopping OSC receiver thread")
        self.server.shutdown()
        self.thread.join(timeout=5)
        # If the thread fails to stop, start yelling at the top of your lungs and happy debugging!
        if self.thread.is_alive():
            logger.error("Failed to stop OSC receiver thread!!!!!!!!")

    def restart(self) -> None:
        self.stop()
        self.restart()
