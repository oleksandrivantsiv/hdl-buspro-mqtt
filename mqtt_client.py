import logging
import threading
import paho.mqtt.client as mqtt


logger = logging.getLogger(__name__)


class MqttClient:

    def __init__(self, host, port, components_ctl):
        self.host = host
        self.port = port
        self.components_ctl = components_ctl
        self.client = mqtt.Client()
        self.client.on_connect = self.on_connect
        self.client.on_message = self.on_message
        self.command_topics = {}
        self.state_topics = {}

        self.client.connect(self.host, self.port)

    # The callback for when the client receives a CONNACK response from the server.
    def on_connect(self, client, userdata, flags, rc):
        logger.info("Connected with result code " + str(rc))

        # Subscribing in on_connect() means that if we lose the connection and
        # reconnect then subscriptions will be renewed.
        client.subscribe("set/#")
        for topic in self.command_topics:
            client.subscribe(f"{topic}/#")

    # The callback for when a PUBLISH message is received from the server.
    def on_message(self, client, userdata, msg):
        logger.debug(msg.topic + " " + str(msg.payload))

        if msg.topic not in self.command_topics:
            logger.info(f"Command topic '{msg.topic}' is not registered")
            return

        self.components_ctl.execute_operation(*self.command_topics[msg.topic], msg.topic, msg.payload.decode())

    def register_command(self, subnet_id, device_id, channel_id, command_topic):
        if command_topic in self.command_topics:
            raise RuntimeError(f"Command topic '{command_topic}' is already registered")
        self.command_topics[command_topic] = (subnet_id, device_id, channel_id)

    def publish(self, topic, op):
        self.client.publish(topic, op.encode())

    def worker(self):
        logger.info("Starting MQTT client")
        self.client.loop_forever()

    def run(self):
        thread = threading.Thread(target=self.worker)
        thread.start()
        return thread
