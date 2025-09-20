import socket
import threading
import logging
import scapy.all as scapy

import hdl_packets
import hdl_listener
import mqtt_client
import scheduler


logger = logging.getLogger("hdl_ctl")


class HDLError(Exception):
    pass


class HDLValidationError(HDLError):
    pass


class HDLUnsupportedOperation(HDLError):
    pass


class HDLChannel:

    def __init__(self, name, parent, channel_id, state_publisher, *args, **kwargs):
        self.lock = threading.Lock()
        self.name = name
        self.parent = parent
        self.channel_id = channel_id

        self.state_publisher = state_publisher

    def get_channel_id(self):
        return self.channel_id

    def validate_operation(self, *args, **kwargs):
        raise NotImplemented()

    def execute_operation(self, *args, **kwargs):
        raise NotImplemented()

    def update(self, *args, **kwargs):
        raise NotImplemented()


class SwitchState:

    def __init__(self, state=0, confirmed=False, last_operation=None):
        self.state = state
        self.confirmed = confirmed
        self.last_operation = last_operation

    def __str__(self):
        return f"{self.state}:{self.confirmed} last oper: {self.last_operation}"


class HDLSingleSwitch(HDLChannel):

    def __init__(self, *args, **kwargs):
        super(HDLSingleSwitch, self).__init__(*args, **kwargs)
        self.state = SwitchState()

        self.update_max_time = 0.2
        self.update_required = False
        self.operations_to_status = {
            kwargs['on_operation']: 100,
            kwargs['off_operation']: 0
        }

        self.command_topic = kwargs['command_topic']
        self.state_topic = kwargs['state_topic']

        self.status_to_operation = {}
        for key, val in self.operations_to_status.items():
            self.status_to_operation[val] = key

        self.state_publisher.register_command(self.parent.subnet_id, self.parent.device_id,
                                              self.channel_id, self.command_topic)

    def validate_operation(self, op):
        return op in self.operations_to_status

    def execute_operation(self, topic, op):
        with self.lock:
            return self._execute_operation_lockless(topic, op)

    def _execute_operation_lockless(self, topic, op):
        if not self.validate_operation(op):
            raise HDLValidationError(f"Unknown operation {op}")

        content = hdl_packets.SingleSwitchControlRequest()
        content.channel = self.channel_id
        content.level = self.operations_to_status[op]

        packet = hdl_packets.HDLSmartBus()
        packet.oper_code = hdl_packets.HDLOperCode.SingleSwitchControlRequest.value
        packet.target_subnet_id = self.parent.subnet_id
        packet.target_device_id = self.parent.device_id
        packet.content = content

        self.state.state = content.level
        self.state.confirmed = False
        self.state.last_operation = op
        self.state_publisher.schedule_delayed_event(self.update_max_time, self.check_status)

        self.state_publisher.send_packet(scapy.raw(packet))

    def update(self, status):
        logger.debug(f"Received state update {self.parent.subnet_id}.{self.parent.device_id}.{self.channel_id} {status}")
        with self.lock:
            self.state.state = status
            self.state.confirmed = True
            self.state.last_operation = None
            self.state_publisher.publish(self.state_topic, self.status_to_operation[status])

    def check_status(self):
        logger.debug(f"check_status: update required {self.update_required}")
        with self.lock:
            if not self.state.confirmed:
                if self.state.last_operation:
                    self._execute_operation_lockless(self.state_topic, self.state.last_operation)
                else:
                    self.parent.request_update()
                    self.state_publisher.schedule_delayed_event(self.update_max_time, self.check_status)


class HDLFloorHeatingChannel(HDLChannel):
    unit_map = {
        'C': 0,
        'F': 1
    }
    status_map = {
        "heat": 1,
        "off": 0
    }
    mode_map = {
        "NORMAL": 1,
        "DAY": 2,
        "NIGHT": 3,
        "AWAY": 4,
        "TIMER": 5,
    }

    def __init__(self, *args, **kwargs):
        super(HDLFloorHeatingChannel, self).__init__(*args, **kwargs)
        self.update_max_time = 1
        self.update_required = {
            hdl_packets.HDLOperCode.ReadTemperatureRequest.value: False,
            hdl_packets.HDLOperCode.ReadFloorHeatingStatusRequest.value: False,
            hdl_packets.HDLOperCode.ControlFloorHeatingStatusResponse.value: False
        }

        self.status = 0
        self.temperature = 0
        self.default_mode = self.mode_map['NORMAL']

        self.temperature_unit = kwargs['temperature_unit']
        self.mode_command_topic = kwargs['mode_command_topic']
        self.mode_state_topic = kwargs['mode_state_topic']
        self.target_temperature_command_topic = kwargs['target_temperature_command_topic']
        self.target_temperature_state_topic = kwargs['target_temperature_state_topic']
        self.current_temperature_topic = kwargs.get('current_temperature_topic')

        self.temperature_sensor_state_topic = None

        self.status_map_inverse = {val: key for key, val in self.status_map.items()}

        self.state_publisher.register_command(self.parent.subnet_id, self.parent.device_id,
                                              self.channel_id, self.mode_command_topic)
        self.state_publisher.register_command(self.parent.subnet_id, self.parent.device_id,
                                              self.channel_id, self.target_temperature_command_topic)

    def add_temperature_sensor(self, state_topic):
        self.temperature_sensor_state_topic = state_topic

    def periodic_temperature_update(self, schedule_only=False):
        if not self.temperature_sensor_state_topic:
            return
        if not schedule_only:
            self.request_temperature_update()
        self.state_publisher.schedule_delayed_event(60 + self.channel_id,
                                                    self.periodic_temperature_update)

    def request_temperature_update(self):
        self.state_publisher.schedule_delayed_event(self.update_max_time, self.check_status)

        read_temp = hdl_packets.HDLSmartBus()
        read_temp.oper_code = hdl_packets.HDLOperCode.ReadTemperatureRequest.value
        read_temp.target_subnet_id = self.parent.subnet_id
        read_temp.target_device_id = self.parent.device_id
        read_temp.content = hdl_packets.ReadTemperatureRequest()
        read_temp.content.channel = self.channel_id

        self.update_required[hdl_packets.HDLOperCode.ReadTemperatureResponse.value] = True
        self.state_publisher.send_packet(scapy.raw(read_temp))

    def request_status_update(self):
        read_status = hdl_packets.HDLSmartBus()
        read_status.oper_code = hdl_packets.HDLOperCode.ReadFloorHeatingStatusRequest.value
        read_status.target_subnet_id = self.parent.subnet_id
        read_status.target_device_id = self.parent.device_id
        read_status.content = hdl_packets.ReadFloorHeatingStatusRequest()
        read_status.content.channel = self.channel_id

        self.update_required[hdl_packets.HDLOperCode.ReadFloorHeatingStatusResponse.value] = True
        self.state_publisher.send_packet(scapy.raw(read_status))

    def request_update(self):
        if self.temperature_sensor_state_topic or self.current_temperature_topic:
            self.state_publisher.schedule_delayed_event((self.parent.device_id % 3) + self.channel_id,
                                                        self.request_temperature_update)
            self.periodic_temperature_update(schedule_only=True)
        self.state_publisher.schedule_delayed_event((self.parent.device_id % 3) + 0.5 + self.channel_id,
                                                    self.request_status_update)

    def validate_operation(self, op):
        return True

    def _execute_operation_lockless(self, topic, op):
        if topic == self.mode_command_topic:
            self.status = self.status_map[op]
        elif topic == self.target_temperature_command_topic:
            self.temperature = int(float(op))
        else:
            raise HDLValidationError(f"Unsupported topic: {topic}")

        content = hdl_packets.ControlFloorHeatingStatusRequest()
        content.channel = self.channel_id
        content.status = self.status
        content.unit = self.unit_map[self.temperature_unit]
        content.mode = self.default_mode
        content.normal_temp = self.temperature
        content.day_temp = self.temperature
        content.night_temp = self.temperature
        content.away_temp = self.temperature
        content.timer = 0
        content.valve = 0
        content.watering_time = 0

        packet = hdl_packets.HDLSmartBus()
        packet.oper_code = hdl_packets.HDLOperCode.ControlFloorHeatingStatusRequest.value
        packet.target_subnet_id = self.parent.subnet_id
        packet.target_device_id = self.parent.device_id
        packet.content = content

        self.update_required[hdl_packets.HDLOperCode.ControlFloorHeatingStatusResponse.value] = True
        self.state_publisher.schedule_delayed_event(self.update_max_time, self.check_status)

        self.state_publisher.send_packet(scapy.raw(packet))

    def execute_operation(self, topic, op):
        with self.lock:
            return self._execute_operation_lockless(topic, op)

    def update(self, oper_code, content):
        with self.lock:
            logger.debug(
                f"Received state update {self.parent.subnet_id}.{self.parent.device_id}.{self.channel_id}")
            if oper_code == hdl_packets.HDLOperCode.ReadTemperatureResponse.value:
                if self.temperature_sensor_state_topic:
                    self.state_publisher.publish(self.temperature_sensor_state_topic, str(float(content.temperature)))

                if self.current_temperature_topic:
                    self.state_publisher.publish(self.current_temperature_topic, str(float(content.temperature)))

                self.update_required[oper_code] = False
                return

            if oper_code == hdl_packets.HDLOperCode.ReadFloorHeatingStatusResponse.value or\
                    oper_code == hdl_packets.HDLOperCode.ControlFloorHeatingStatusResponse.value:
                self.status = content.status
                self.state_publisher.publish(self.mode_state_topic, self.status_map_inverse[self.status])

                if content.mode_map[content.mode] == 'NORMAL':
                    self.temperature = content.normal_temp
                elif content.mode_map[content.mode] == 'DAY':
                    self.temperature = content.day_temp
                elif content.mode_map[content.mode] == 'NIGHT':
                    self.temperature = content.night_temp
                elif content.mode_map[content.mode] == 'AWAY':
                    self.temperature = content.away_temp

                self.state_publisher.publish(self.target_temperature_state_topic, str(float(self.temperature)))
                self.update_required[hdl_packets.HDLOperCode.ReadFloorHeatingStatusResponse.value] = False
                self.update_required[hdl_packets.HDLOperCode.ControlFloorHeatingStatusResponse.value] = False

    def check_status(self):
        with self.lock:
            for oper_code, status in self.update_required.items():
                if status:
                    if oper_code == hdl_packets.HDLOperCode.ReadTemperatureResponse.value:
                        self.request_temperature_update()
                    elif oper_code == hdl_packets.HDLOperCode.ReadFloorHeatingStatusResponse.value or \
                            oper_code == hdl_packets.HDLOperCode.ControlFloorHeatingStatusResponse.value:
                        self.request_status_update()
                    self.state_publisher.schedule_delayed_event(self.update_max_time, self.check_status)

    def run(self):
        self.request_update()


class HDLDevice:

    def __init__(self, subnet_id, device_id, state_publisher):
        self.subnet_id = subnet_id
        self.device_id = device_id
        self.channels = {}

        self.state_publisher = state_publisher

    def get_id(self):
        return self.subnet_id, self.device_id

    def update(self, *args, **kwargs):
        raise NotImplemented()

    def execute_operation(self, channel, op):
        raise NotImplemented()

    def request_update(self):
        raise NotImplemented()

    def run(self):
        raise NotImplemented()

    def add_channel(self, channel):
        channel_id = channel.get_channel_id()
        if channel_id in self.channels:
            raise HDLValidationError(f"Channel {channel_id} already exists")

        self.channels[channel_id] = channel


class HDLFloorHeating(HDLDevice):

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

    def add_temperature_sensor(self, subnet_id, device_id, channel_id, state_topic):
        if channel_id not in self.channels:
            raise HDLValidationError(f"Unknown temperature sensor channel {subnet_id}.{device_id}.{channel_id}")

        self.channels[channel_id].add_temperature_sensor(state_topic)

    def request_update(self):
        pass

    def update(self, packet):
        if packet.oper_code == hdl_packets.HDLOperCode.ReadFloorHeatingStatusResponse.value:
            content = hdl_packets.ReadFloorHeatingStatusResponse(packet.content)
        elif packet.oper_code == hdl_packets.HDLOperCode.ControlFloorHeatingStatusResponse.value:
            content = hdl_packets.ControlFloorHeatingStatusResponse(packet.content)
        elif packet.oper_code == hdl_packets.HDLOperCode.ReadTemperatureResponse.value:
            content = hdl_packets.ReadTemperatureResponse(packet.content)
        else:
            raise HDLUnsupportedOperation(f"Unsupported operation {hex(packet.oper_code)}")

        if content.channel not in self.channels:
            raise HDLValidationError(f"Received update for unregistered device {content.channel}")

        self.channels[content.channel].update(packet.oper_code, content)

    def execute_operation(self, channel, *args, **kwargs):
        if channel not in self.channels:
            raise HDLValidationError(f"Channel {channel} is not registered in device {self.subnet_id, self.device_id}")

        self.channels[channel].execute_operation(*args, **kwargs)

    def run(self):
        for channel in self.channels.values():
            channel.run()


class HDLRelay(HDLDevice):

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

    def request_update(self):
        read_status = hdl_packets.HDLSmartBus()
        read_status.oper_code = hdl_packets.HDLOperCode.ReadStatusOfChannelsRequest.value
        read_status.target_subnet_id = self.subnet_id
        read_status.target_device_id = self.device_id

        self.state_publisher.send_packet(scapy.raw(read_status))

    def update(self, packet):
        if packet.oper_code == hdl_packets.HDLOperCode.ReadStatusOfChannelsResponse.value:
            # self.update_required = False
            content = hdl_packets.ReadStatusOfChannelsResponse(packet.content)
            for channel_id, status in enumerate(list(content.channels), start=1):
                if channel_id not in self.channels:
                    continue
                self.channels[channel_id].update(status)

        elif packet.oper_code == hdl_packets.HDLOperCode.SingleSwitchControlResponse.value:
            content = hdl_packets.SingleSwitchControlResponse(packet.content)
            if content.channel not in self.channels:
                return
            self.channels[content.channel].update(content.level)
        else:
            raise HDLUnsupportedOperation(f"Unsupported operation {packet.oper_code}")

    def execute_operation(self, channel, *args, **kwargs):
        if channel not in self.channels:
            raise HDLValidationError(
                f"Channel {channel} is not registered in device {self.subnet_id, self.device_id}")

        self.channels[channel].execute_operation(*args, **kwargs)

    def periodic_update(self):
        self.request_update()
        self.state_publisher.schedule_delayed_event(10, self.periodic_update)

    def run(self):
        self.periodic_update()


class ComponentCtl:

    def __init__(self, hdl_host, hdl_port, mqtt_host, mqtt_port):
        self.hdl_host = hdl_host
        self.hdl_port = hdl_port
        self.mqtt_host = mqtt_host
        self.mqtt_port = mqtt_port
        self.scheduler = scheduler.Scheduler()

        self.devices = {}
        self.hdl_listener = hdl_listener.HDLListener('0.0.0.0', hdl_port, self)
        self.mqtt_client = mqtt_client.MqttClient(mqtt_host, mqtt_port, self)

    def add_device(self, device):
        dev_id = device.get_id()
        if dev_id in self.devices:
            raise HDLValidationError(f"Device {dev_id} already exists.")

        self.devices[dev_id] = device

    def update(self, data):
        try:
            packet = hdl_packets.HDLSmartBus(data)
            dev_id = packet.orig_subnet_id, packet.orig_device_id
            if dev_id not in self.devices:
                return

            self.devices[dev_id].update(packet)
        except HDLUnsupportedOperation as e:
            logger.debug(e)
        except HDLValidationError as e:
            logger.error(e)
        except Exception as e:
            logger.error(f"Unknown exception: {e}")

    def execute_operation(self, subnet_id, device_id, channel, *args, **kwargs):
        logger.debug(f"Schedule operation execution {subnet_id}.{device_id}.{channel}: args {args} kwargs {kwargs}")

        def _execute_operation_callback():
            logger.debug(f"Operation execution callback {subnet_id}.{device_id}.{channel}: args {args} kwargs {kwargs}")
            dev_id = subnet_id, device_id
            if dev_id not in self.devices:
                return

            self.devices[dev_id].execute_operation(channel, *args, **kwargs)

        self.schedule_event(_execute_operation_callback)

    def publish(self, topic, op):
        self.mqtt_client.publish(topic, op)

    def schedule_event(self, callback):
        self.scheduler.schedule_event(delay=0, priority=0, callback=callback)

    def schedule_delayed_event(self, delay, callback):
        self.scheduler.schedule_event(delay=delay, priority=1, callback=callback)

    def register_command(self, subnet_id, device_id, channel_id, command_topic):
        self.mqtt_client.register_command(subnet_id, device_id, channel_id, command_topic)

    def send_packet(self, data):
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
                sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
                sock.sendto(data, (self.hdl_host, self.hdl_port))
        except Exception as ex:
            logger.error(f"Failed to send packet: {ex}")
            raise ex

    def run(self):
        threads = [
            self.scheduler.run(),
            self.hdl_listener.run(),
            self.mqtt_client.run()
        ]

        for dev in self.devices.values():
            dev.run()

        for t in threads:
            t.join()
