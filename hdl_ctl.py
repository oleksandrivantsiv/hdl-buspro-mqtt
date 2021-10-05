#!/usr/bin/env python3

import ipaddress
import logging

import click
import yaml

import hdl_component

logging.basicConfig()
logging.root.setLevel(hdl_component.logging.INFO)

logger = hdl_component.logging.getLogger(__name__)


class Include(yaml.YAMLObject):
    yaml_loader = yaml.SafeLoader
    yaml_tag = '!include'

    def __init__(self, val):
        self.val = val

    @classmethod
    def from_yaml(cls, loader, node):
        return cls(node.value)


def read_config_file(path_to_file):
    with open(path_to_file, 'r') as config_file:
        try:
            return yaml.safe_load(config_file)
        except yaml.YAMLError as e:
            hdl_component.logger.info(e)


@click.command()
@click.option('--hdl-host', type=ipaddress.ip_address, default='0.0.0.0')
@click.option('--hdl-port', type=int, default=6000)
@click.option('--mqtt-host', type=ipaddress.ip_address, default='127.0.0.1')
@click.option('--mqtt-port', type=int, default=1883)
@click.option('--verbose', is_flag=True, default=False)
@click.argument('home-assistant-cfg', type=click.Path(), required=True)
def main(hdl_host, hdl_port, mqtt_host, mqtt_port, verbose, home_assistant_cfg):
    if verbose:
        hdl_component.logging.root.setLevel(hdl_component.logging.DEBUG)

    components_ctl = hdl_component.ComponentCtl(str(hdl_host), hdl_port, str(mqtt_host), mqtt_port)
    config_file = read_config_file(home_assistant_cfg)

    devices = {}

    for dev in config_file['light']:
        if dev['platform'] != 'mqtt':
            logger.error(f"Unsupported device {dev}")
            continue
        subnet_id, device_id, channel = [int(i) for i in dev['unique_id'].split('.')]
        if (subnet_id, device_id) not in devices:
            devices[(subnet_id, device_id)] = hdl_component.HDLRelay(subnet_id, device_id, components_ctl)
            components_ctl.add_device(devices[(subnet_id, device_id)])
        devices[(subnet_id, device_id)].add_channel(
            hdl_component.HDLSingleSwitch(dev['name'], devices[(subnet_id, device_id)], channel, components_ctl,
                                          command_topic=dev['command_topic'],
                                          state_topic=dev['state_topic'],
                                          on_operation=dev['payload_on'],
                                          off_operation=dev['payload_off']))

    for dev in config_file['climate']:
        if dev['platform'] != 'mqtt':
            continue
        subnet_id, device_id, channel = [int(i) for i in dev['unique_id'].split('.')]
        if (subnet_id, device_id) not in devices:
            devices[(subnet_id, device_id)] = hdl_component.HDLFloorHeating(subnet_id, device_id, components_ctl)
            components_ctl.add_device(devices[(subnet_id, device_id)])
        devices[(subnet_id, device_id)].add_channel(
            hdl_component.HDLFloorHeatingChannel(dev['name'], devices[(subnet_id, device_id)], channel, components_ctl,
                                                 temperature_unit=dev['temperature_unit'],
                                                 mode_command_topic=dev['mode_command_topic'],
                                                 mode_state_topic=dev['mode_state_topic'],
                                                 target_temperature_command_topic=dev['temperature_command_topic'],
                                                 target_temperature_state_topic=dev['temperature_state_topic'],
                                                 current_temperature_topic=dev['current_temperature_topic']))

    for dev in config_file['sensor']:
        if dev['platform'] != 'mqtt':
            continue
        subnet_id, device_id, channel = [int(i) for i in dev['unique_id'].split('.')]

        if (subnet_id, device_id) not in devices:
            raise RuntimeError(f"No requested climate device {subnet_id}.{device_id} found")

        devices[(subnet_id, device_id)].add_temperature_sensor(subnet_id, device_id, channel,
                                                               state_topic=dev['state_topic'])

    components_ctl.run()


if __name__ == '__main__':
    main()
