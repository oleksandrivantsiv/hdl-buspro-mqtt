#!/usr/bin/python

import enum
import struct
from scapy.all import *


def crc16xmodem(data):
    """Pure-Python CRC-16/XMODEM implementation.
    Accepts bytes or str, returns 16-bit int.
    """
    if isinstance(data, str):
        data = data.encode()

    crc = 0x0000
    for b in data:
        if isinstance(b, str):
            b = ord(b)
        crc ^= (b << 8)
        for _ in range(8):
            if crc & 0x8000:
                crc = ((crc << 1) ^ 0x1021) & 0xFFFF
            else:
                crc = (crc << 1) & 0xFFFF
    return crc


class HDLOperCode(enum.Enum):
    SingleSwitchControlRequest = 0x0031
    SingleSwitchControlResponse = 0x0032
    ReadStatusOfChannelsRequest = 0x0033
    ReadStatusOfChannelsResponse = 0x0034
    ReadFloorHeatingStatusRequest = 0x1C5E
    ReadFloorHeatingStatusResponse = 0x1C5F
    ControlFloorHeatingStatusRequest = 0x1C5C
    ControlFloorHeatingStatusResponse = 0x1C5D
    ReadTemperatureRequest = 0xE3E7
    ReadTemperatureResponse = 0xE3E8


class HDLSmartBus(Packet):
    name = "HDLSmartBus"
    fields_desc = [
        XShortField("preamble0", 0xc0a8),
        XShortField("preamble1", 0x0114),
        XShortField("preamble2", 0x4844),
        XShortField("preamble3", 0x4c4d),
        XShortField("preamble4", 0x4952),
        XShortField("preamble5", 0x4143),
        XShortField("preamble6", 0x4c45),
        XShortField("leading_code", 0xaaaa),
        FieldLenField("length", None, length_of="content", fmt='B'),
        XByteField("orig_subnet_id", 0xfc),
        XByteField("orig_device_id", 0xfc),
        XShortField("orig_device_type", 0xfffc),
        XShortField("oper_code", None),
        XByteField("target_subnet_id", None),
        XByteField("target_device_id", None),
        StrLenField("content", None, length_from=lambda pkt: pkt.length-11),
        XShortField("crc", None)
    ]

    preamble_len = 16
    crc_len = 2

    def post_build(self, p, pay):
        if self.length is None:
            tmp_len = len(p) - self.preamble_len + len(pay)
            p = p[:16] + struct.pack("!B", tmp_len & 0xff) + p[17:]

        if self.crc is None:
            data = p[HDLSmartBus.preamble_len:-HDLSmartBus.crc_len]
            crc = crc16xmodem(data)
            p = p[:-2] + struct.pack("!H", crc)

        return p + pay


class SingleSwitchControlRequest(Packet):
    name = "SingleSwitchControlRequest"
    operation_map = {
        100: "ON",
        0: "OFF"
    }
    fields_desc = [
        ByteField("channel", None),
        ByteEnumField("level", None, operation_map),
        XShortField("padding", 0),
    ]


class SingleSwitchControlResponse(Packet):
    name = "SingleSwitchControlResponse"
    operation_map = {
        100: "ON",
        0: "OFF"
    }
    fields_desc = [
        ByteField("channel", None),
        ByteEnumField("return_code", None, operation_map),
        ByteEnumField("level", None, operation_map),
        XByteField("padding0", 0),
        XByteField("padding1", 0),
        XByteField("padding2", 0),
    ]


class ReadStatusOfChannelsResponse(Packet):
    name = "ReadStatusOfChannelsResponse"
    operation_map = {
        100: "ON",
        0: "OFF"
    }
    fields_desc = [
        FieldLenField("length", None, length_of="content", fmt='B'),
        StrLenField("channels", None, length_from=lambda pkt: pkt.length),
    ]


class ReadFloorHeatingStatusRequest(Packet):
    name = "ReadFloorHeatingStatusRequest"

    fields_desc = [
        ByteField("channel", None)
    ]


class ReadFloorHeatingStatusResponse(Packet):
    name = "ReadFloorHeatingStatusResponse"
    status_map = {
        0: "OFF",
        1: "ON"
    }
    temp_unit_map = {
        0: "CELS",
        1: "FAHR"
    }
    mode_map = {
        1: "NORMAL",
        2: "DAY",
        3: "NIGHT",
        4: "AWAY",
        5: "TIMER"
    }
    fields_desc = [
        ByteField("channel", None),
        ByteEnumField("status", None, status_map),
        ByteEnumField("unit", None, temp_unit_map),
        ByteEnumField("mode", None, mode_map),
        ByteField("normal_temp", None),
        ByteField("day_temp", None),
        ByteField("night_temp", None),
        ByteField("away_temp", None),
        XShortField("timer", None),
        XShortField("valve", None),
        XShortField("pwd", None),
        XShortField("watering", None),
        XShortField("watering_time", None),
    ]


class ControlFloorHeatingStatusRequest(Packet):
    name = "ControlFloorHeatingStatusRequest"
    status_map = {
        0: "OFF",
        1: "ON"
    }
    temp_unit_map = {
        0: "CELS",
        1: "FAHR"
    }
    mode_map = {
        1: "NORMAL",
        2: "DAY",
        3: "NIGHT",
        4: "AWAY",
        5: "TIMER"
    }
    fields_desc = [
        ByteField("channel", None),
        ByteEnumField("status", None, status_map),
        ByteEnumField("unit", None, temp_unit_map),
        ByteEnumField("mode", None, mode_map),
        ByteField("normal_temp", None),
        ByteField("day_temp", None),
        ByteField("night_temp", None),
        ByteField("away_temp", None),
        XShortField("timer", None),
        XShortField("valve", None),
        XShortField("watering_time", None),
    ]


class ControlFloorHeatingStatusResponse(ControlFloorHeatingStatusRequest):
    name = "ControlFloorHeatingStatusResponse"


class ReadTemperatureRequest(Packet):
    name = "ReadTemperatureRequest"

    fields_desc = [
        ByteField("channel", None)
    ]


class ReadTemperatureResponse(Packet):
    name = "ReadTemperatureResponse"

    fields_desc = [
        ByteField("channel", None),
        BitField("sign", 0, 1),
        BitField("temperature", 0, 7),
    ]