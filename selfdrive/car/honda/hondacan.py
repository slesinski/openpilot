import struct #Clarity
import common.numpy_fast as np #Clarity
from selfdrive.config import Conversions as CV
from selfdrive.car.honda.values import CAR, HONDA_BOSCH #Clarity

#Clarity
# *** Honda specific ***
def can_cksum(mm):
  s = 0
  for c in mm:
    s += (c>>4)
    s += c & 0xF
  s = 8-s
  s %= 0x10
  return s

#Clarity
def fix(msg, addr):
  msg2 = msg[0:-1] + (msg[-1] | can_cksum(struct.pack("I", addr)+msg)).to_bytes(1, 'little')
  return msg2

def get_pt_bus(car_fingerprint, has_relay):
  return 1 if car_fingerprint in HONDA_BOSCH and has_relay else 0


def get_lkas_cmd_bus(car_fingerprint, has_relay):
  return 2 if car_fingerprint in HONDA_BOSCH and not has_relay else 0

#Clarity
def make_can_msg(addr, dat, idx, alt):
  if idx is not None:
    dat += (int(idx) << 4).to_bytes(1,'little')
    dat = fix(dat, addr)
  return [addr, 0, dat, alt]
  
#Clarity
def create_brake_command(packer, apply_brake, pcm_override, pcm_cancel_cmd, fcw, idx, car_fingerprint, has_relay, stock_brake):
  # TODO: do we loose pressure if we keep pump off for long?
  commands = [] #Clarity
  pump_on = apply_brake > 0 #Clarity: The brake pump algo causes bad braking performance, so we just leave the pump on if the brakes are being called.
  brakelights = apply_brake > 0
  brake_rq = apply_brake > 0
  pcm_fault_cmd = False

  #Clarity
  if car_fingerprint == CAR.CLARITY:
    bus = 2
    # This a bit of a hack but clarity brake msg flows into the last byte so
    # rather than change the fix() function just set accordingly here.
    apply_brake >>= 1
    if apply_brake & 1:
      idx += 0x8


  values = {
    "COMPUTER_BRAKE": apply_brake,
    "BRAKE_PUMP_REQUEST": pump_on,
    "CRUISE_OVERRIDE": pcm_override,
    "CRUISE_FAULT_CMD": pcm_fault_cmd,
    "CRUISE_CANCEL_CMD": pcm_cancel_cmd,
    "COMPUTER_BRAKE_REQUEST": brake_rq,
    "SET_ME_1": 1,
    "BRAKE_LIGHTS": brakelights,
    "CHIME": 1 if fcw else 0,  #Clarity: This calls on stock_brake[] and causes a DANGEROUS crash during fcw. Chime = 1 is beeping, Chime = 2 is constant tone. -wirelessnet2
    "FCW": fcw << 1,  # TODO: Why are there two bits for fcw?
    "AEB_REQ_1": 0,
    "AEB_REQ_2": 0,
    "AEB_STATUS": 0,
  }
  #bus = get_pt_bus(car_fingerprint, has_relay)
  #return packer.make_can_msg("BRAKE_COMMAND", bus, values, idx)
  commands.append(packer.make_can_msg("BRAKE_COMMAND", bus, values, idx))
  return commands


def create_steering_control(packer, apply_steer, lkas_active, car_fingerprint, idx, has_relay):
  values = {
    "STEER_TORQUE": apply_steer if lkas_active else 0,
    "STEER_TORQUE_REQUEST": lkas_active,
  }
  #bus = get_lkas_cmd_bus(car_fingerprint, has_relay)
  bus = 2 #Clarity
  return packer.make_can_msg("STEERING_CONTROL", bus, values, idx)


def create_ui_commands(packer, pcm_speed, hud, car_fingerprint, is_metric, idx, has_relay, stock_hud):
  commands = []
  #Clarity
  #bus_pt = get_pt_bus(car_fingerprint, has_relay)
  #bus_lkas = get_lkas_cmd_bus(car_fingerprint, has_relay)
  bus_pt = 2
  bus_lkas = 2

  if car_fingerprint not in HONDA_BOSCH:
    acc_hud_values = {
      'PCM_SPEED': pcm_speed * CV.MS_TO_KPH,
      'PCM_GAS': hud.pcm_accel,
      'CRUISE_SPEED': hud.v_cruise,
      'ENABLE_MINI_CAR': 1,
      'HUD_LEAD': hud.car,
      'HUD_DISTANCE': 3,    # max distance setting on display
      'IMPERIAL_UNIT': int(not is_metric),
      'SET_ME_X01_2': 1,
      'SET_ME_X01': 1,
      "FCM_OFF": 0, #CLarity: This call on stock_hud[] and causes a crash. -wirelessnet2
      "FCM_OFF_2": 0, #CLarity: This call on stock_hud[] and causes a crash. -wirelessnet2
      "FCM_PROBLEM": 0, #CLarity: This call on stock_hud[] and causes a crash. -wirelessnet2
      "ICONS": 0, #CLarity: This call on stock_hud[] and causes a crash. -wirelessnet2
    }
    commands.append(packer.make_can_msg("ACC_HUD", bus_pt, acc_hud_values, idx))

  lkas_hud_values = {
    'SET_ME_X41': 0x41,
    'SET_ME_X48': 0x48,
    'STEERING_REQUIRED': hud.steer_required,
    'SOLID_LANES': hud.lanes,
    'BEEP': 0,
  }
  commands.append(packer.make_can_msg('LKAS_HUD', bus_lkas, lkas_hud_values, idx))

  return commands

#Clarity: Since we don't have a factory ADAS Camera to drive the Radar, we have to create the messages ourselves. -wirelessnet2
def create_radar_commands(packer, v_ego, car_fingerprint, new_radar_config, idx):
  """Creates an iterable of CAN messages for the radar system."""
  radar_bus = 1
  commands = []
  v_ego_kph = np.clip(int(round(v_ego * CV.MS_TO_KPH)), 0, 255)
  speed = struct.pack('!B', v_ego_kph)

  msg300 = {
    'SET_ME_XF9': 0xF9,
    'VEHICLE_SPEED': 0x00,
    'SET_ME_X8A': 0x8A,
    'SET_ME_XD0': 0xD0,
    'SALTED_WITH_IDX': 0x20 if idx == 0 or idx == 3 else 0x00,
  }

  msg301 = {
    'SET_ME_X5D': 0x5D, #This is 1/3 of the VEHICLE STATE MSG for the Clarity. -wirelessnet2
    'SET_ME_X02': 0x02, #This is 1/3 of the VEHICLE STATE MSG for the Clarity. -wirelessnet2
    'SET_ME_X5F': 0x5F, #This is 1/3 of the VEHICLE STATE MSG for the Clarity. -wirelessnet2
  }

  commands.append(packer.make_can_msg('VEHICLE_STATE', radar_bus, msg300, idx))
  commands.append(packer.make_can_msg('VEHICLE_STATE2', radar_bus, msg301, idx))
  #Energee has saved our ass again. All hail energeeeeeeeeeeee -wirelessnet2
  
  return commands

def spam_buttons_command(packer, button_val, idx, car_fingerprint, has_relay):
  values = {
    'CRUISE_BUTTONS': button_val,
    'CRUISE_SETTING': 0,
  }
  bus = get_pt_bus(car_fingerprint, has_relay)
  return packer.make_can_msg("SCM_BUTTONS", bus, values, idx)
