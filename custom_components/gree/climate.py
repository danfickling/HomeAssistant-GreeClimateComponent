#!/usr/bin/python
# Do basic imports
import socket
import base64

import logging
import voluptuous as vol
import homeassistant.helpers.config_validation as cv

from homeassistant.components.climate import (
    ClimateEntity,
    ClimateEntityFeature,
    HVACMode,
    PLATFORM_SCHEMA
)

from homeassistant.const import (
    ATTR_TEMPERATURE, 
    ATTR_UNIT_OF_MEASUREMENT,
    CONF_HOST,
    CONF_MAC,
    CONF_NAME,
    CONF_PORT,
    CONF_TIMEOUT,
    STATE_OFF, 
    STATE_ON,
    STATE_UNKNOWN
)

from homeassistant.core import Event, EventStateChangedData, callback
from homeassistant.helpers.event import async_track_state_change_event
from Crypto.Cipher import AES
try: import simplejson
except ImportError: import json as simplejson
from datetime import timedelta

REQUIREMENTS = ['pycryptodome']

_LOGGER = logging.getLogger(__name__)

SUPPORT_FLAGS = ClimateEntityFeature.TARGET_TEMPERATURE | ClimateEntityFeature.FAN_MODE | ClimateEntityFeature.TURN_ON | ClimateEntityFeature.TURN_OFF

DEFAULT_NAME = 'Gree Climate'

CONF_TARGET_TEMP_STEP = 'target_temp_step'
CONF_TEMP_SENSOR = 'temp_sensor'
CONF_POWERSAVE = 'powersave'
CONF_ENCRYPTION_KEY = 'encryption_key'
CONF_UID = 'uid'
CONF_TARGET_TEMP = 'target_temp'
CONF_ENCRYPTION_VERSION = 'encryption_version'
CONF_DISABLE_AVAILABLE_CHECK  = 'disable_available_check'
CONF_MAX_ONLINE_ATTEMPTS = 'max_online_attempts'

DEFAULT_PORT = 7000
DEFAULT_TIMEOUT = 10
DEFAULT_TARGET_TEMP_STEP = 1

# from the remote control and gree app
MIN_TEMP = 16
MAX_TEMP = 30

# update() interval
SCAN_INTERVAL = timedelta(seconds=60)

TEMP_OFFSET  = 40

# fixed values in gree mode lists
HVAC_MODES = [HVACMode.AUTO, HVACMode.COOL, HVACMode.HEAT, HVACMode.DRY, HVACMode.FAN_ONLY, HVACMode.OFF]

FAN_MODES = ['Auto', 'Low', 'Medium-Low', 'Medium', 'Medium-High', 'High', 'Turbo', 'Quiet']

GCM_IV = b'\x54\x40\x78\x44\x49\x67\x5a\x51\x6c\x5e\x63\x13'
GCM_ADD = b'qualcomm-test'

PLATFORM_SCHEMA = PLATFORM_SCHEMA.extend({
    vol.Optional(CONF_NAME, default=DEFAULT_NAME): cv.string,
    vol.Required(CONF_HOST): cv.string,
    vol.Required(CONF_PORT, default=DEFAULT_PORT): cv.positive_int,
    vol.Required(CONF_MAC): cv.string,
    vol.Optional(CONF_TIMEOUT, default=DEFAULT_TIMEOUT): cv.positive_int,
    vol.Optional(CONF_TARGET_TEMP_STEP, default=DEFAULT_TARGET_TEMP_STEP): vol.Coerce(float),
    vol.Optional(CONF_TEMP_SENSOR): cv.entity_id,
    vol.Optional(CONF_POWERSAVE): cv.entity_id,
    vol.Optional(CONF_ENCRYPTION_KEY): cv.string,
    vol.Optional(CONF_UID): cv.positive_int,
    vol.Optional(CONF_TARGET_TEMP): cv.entity_id,
    vol.Optional(CONF_ENCRYPTION_VERSION, default=1): cv.positive_int,
    vol.Optional(CONF_DISABLE_AVAILABLE_CHECK, default=False): cv.boolean,
    vol.Optional(CONF_MAX_ONLINE_ATTEMPTS, default=3): cv.positive_int
})

async def async_setup_platform(hass, config, async_add_devices, discovery_info=None):
    """Set up the Gree climate devices."""
    _LOGGER.info('Setting up Gree climate platform')
    
    # Get the base MAC address and other config
    mac_base = config.get(CONF_MAC).encode().replace(b':', b'')
    encryption_key = config.get(CONF_ENCRYPTION_KEY)
    encryption_version = config.get(CONF_ENCRYPTION_VERSION)
    
    # If no encryption key provided, get it using base MAC
    if not encryption_key:
        _LOGGER.info('No encryption key provided, fetching from device')
        base_device = GreeClimate(
            hass=hass,
            name="Base Device",
            ip_addr=config.get(CONF_HOST),
            port=config.get(CONF_PORT),
            mac_addr=mac_base,
            timeout=config.get(CONF_TIMEOUT),
            target_temp_step=None,
            temp_sensor_entity_id=None,
            powersave_entity_id=None,
            target_temp_entity_id=None,
            hvac_modes=HVAC_MODES,
            fan_modes=FAN_MODES,
            encryption_version=encryption_version,
            disable_available_check=True,
            max_online_attempts=1,
            encryption_key=None,
            uid=config.get(CONF_UID),
            is_main_unit=True  # Added flag for main unit
        )
        
        if encryption_version == 1:
            if not base_device.GetDeviceKey():
                _LOGGER.error("Failed to get encryption key")
                return
            encryption_key = base_device._encryption_key.decode('utf-8')
        elif encryption_version == 2:
            if not base_device.GetDeviceKeyGCM():
                _LOGGER.error("Failed to get encryption key")
                return
            encryption_key = base_device._encryption_key.decode('utf-8')
        else:
            _LOGGER.error('Encryption version %s is not implemented.', encryption_version)
            return
            
        _LOGGER.info('Successfully retrieved encryption key: %s', encryption_key)
    
    # Create devices list
    devices = []
    
    # Create entities for all 8 potential units
    for unit in range(8):
        unit_mac = mac_base + str(unit).zfill(2).encode()
        unit_name = f"{config.get(CONF_NAME)} Unit {unit}"
        
        # Determine if this is the main unit (unit 0)
        is_main_unit = (unit == 0)
        
        device = GreeClimate(
            hass=hass,
            name=unit_name,
            ip_addr=config.get(CONF_HOST),
            port=config.get(CONF_PORT),
            mac_addr=unit_mac,
            timeout=config.get(CONF_TIMEOUT),
            target_temp_step=config.get(CONF_TARGET_TEMP_STEP),
            temp_sensor_entity_id=config.get(CONF_TEMP_SENSOR) if not is_main_unit else None,  # No temp control for main unit
            powersave_entity_id=config.get(CONF_POWERSAVE),
            target_temp_entity_id=config.get(CONF_TARGET_TEMP) if not is_main_unit else None,  # No temp control for main unit
            hvac_modes=HVAC_MODES,
            fan_modes=FAN_MODES,
            encryption_version=encryption_version,
            disable_available_check=config.get(CONF_DISABLE_AVAILABLE_CHECK),
            max_online_attempts=config.get(CONF_MAX_ONLINE_ATTEMPTS),
            encryption_key=encryption_key,
            uid=config.get(CONF_UID),
            is_main_unit=is_main_unit  # Pass the flag to the device
        )
        devices.append(device)

    async_add_devices(devices)

class GreeClimate(ClimateEntity):
    def __init__(self, hass, name, ip_addr, port, mac_addr, timeout, target_temp_step, temp_sensor_entity_id, powersave_entity_id, target_temp_entity_id, hvac_modes, fan_modes, encryption_version, disable_available_check, max_online_attempts, encryption_key=None, uid=None, is_main_unit=False):
        """Initialize the Gree climate device."""
        self.hass = hass
        self._name = name
        self._ip_addr = ip_addr
        self._port = port
        self._mac_addr = mac_addr.decode('utf-8').lower()
        self._timeout = timeout
        self._unique_id = 'climate.gree_' + mac_addr.decode('utf-8').lower()
        self._device_online = None
        self._online_attempts = 0
        self._max_online_attempts = max_online_attempts
        self._disable_available_check = disable_available_check
        self._is_main_unit = is_main_unit
        self._temperature_unit = '°C'

        # Initialize _acOptions with default values
        self._acOptions = {
            'Pow': 0,  # Default to power off
            'Mod': 0,  # Default to first mode
            'StTem': 0,  # Default temperature setting
            'WdSpd': 0,  # Default fan speed
            'Quier': 0,  # Default quiet mode off
            'EnSvSt': 0,  # Default energy save off
        }

        # Only set up temperature control for secondary units
        if not self._is_main_unit:
            self._target_temperature = None
            self._target_temperature_step = target_temp_step
            self._temp_sensor_entity_id = temp_sensor_entity_id
            self._target_temp_entity_id = target_temp_entity_id
            self._has_temp_sensor = None
            self._current_temperature = None
        else:
            self._target_temperature = None
            self._target_temperature_step = None
            self._temp_sensor_entity_id = None
            self._target_temp_entity_id = None
            self._has_temp_sensor = None
            self._current_temperature = None

        self._hvac_modes = hvac_modes
        self._hvac_mode = HVACMode.OFF
        
        # Only set up fan modes for main unit
        if self._is_main_unit:
            self._fan_modes = fan_modes
            self._fan_mode = self._fan_modes[0] if fan_modes else None
        else:
            self._fan_modes = None
            self._fan_mode = None
        
        self._powersave_entity_id = powersave_entity_id
        self._current_powersave = None
        self._firstTimeRun = True

        self.encryption_version = encryption_version

        # If encryption key provided, set it up immediately
        if encryption_key:
            _LOGGER.info('Using configured encryption key: %s', encryption_key)
            self._encryption_key = encryption_key.encode("utf8")
            if encryption_version == 1:
                self.CIPHER = AES.new(self._encryption_key, AES.MODE_ECB)
            elif encryption_version == 2:
                # GCM cipher will be created as needed
                pass
            else:
                _LOGGER.error('Encryption version %s is not implemented.', encryption_version)
        else:
            self._encryption_key = None
            self.CIPHER = None
        
        if uid:
            self._uid = uid
        else:
            self._uid = 0
        
        self._acOptions = { 'Pow': None, 'Mod': None, 'StTem': None, 'WdSpd': None,  'Dry': None, 'EnSvSt': None, 'StFahFlg': None, 'ColdMod': None, 'HeatSvStTemMax': None, 'CoolSvStTemMin': None, 'Dred': None, 'AppTimer': None, 'TemUnit': None, 'IndoorType': None, 'OMod': None, 'LowDeHumi': None, 'Quier': None, 'RmType': None, 'RmNum': None, 'VavleAllOn': None, 'CSvStTemMinFlg': None, 'HSvStTemMaxFlg': None, 'AllErr': None, 'InProtocol': None, 'Demand': None, 'IntProVer': None, 'MainConProVer': None, 'SubConProVer': None }
        self._optionsToFetch = ["Pow","Mod","StTem","WdSpd","Dry","EnSvSt","StFahFlg","ColdMod","HeatSvStTemMax","CoolSvStTemMin","Dred","AppTimer","TemUnit","IndoorType","OMod","LowDeHumi","Quier","RmType","RmNum","VavleAllOn","CSvStTemMinFlg","HSvStTemMaxFlg","AllErr","InProtocol","Demand","IntProVer","MainConProVer","SubConProVer"]
        
        if temp_sensor_entity_id:
            _LOGGER.info('Setting up temperature sensor: ' + str(temp_sensor_entity_id))
            async_track_state_change_event(hass, temp_sensor_entity_id, self._async_temp_sensor_changed)    

        if powersave_entity_id:
            _LOGGER.info('Setting up powersave entity: ' + str(powersave_entity_id))
            async_track_state_change_event(hass, powersave_entity_id, self._async_powersave_entity_state_changed)

        if target_temp_entity_id:
            _LOGGER.info('Setting up target temp entity: ' + str(target_temp_entity_id))
            async_track_state_change_event(hass, target_temp_entity_id, self._async_target_temp_entity_state_changed)

    # Pad helper method to help us get the right string for encrypting
    def Pad(self, s):
        aesBlockSize = 16
        return s + (aesBlockSize - len(s) % aesBlockSize) * chr(aesBlockSize - len(s) % aesBlockSize)            

    def FetchResult(self, cipher, ip_addr, port, timeout, json):
        _LOGGER.debug('Fetching(%s, %s, %s, %s)' % (ip_addr, port, timeout, json))
        clientSock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        clientSock.settimeout(timeout)
        clientSock.sendto(bytes(json, "utf-8"), (ip_addr, port))
        data, addr = clientSock.recvfrom(64000)
        receivedJson = simplejson.loads(data)
        clientSock.close()
        pack = receivedJson['pack']
        base64decodedPack = base64.b64decode(pack)
        decryptedPack = cipher.decrypt(base64decodedPack)
        if self.encryption_version == 2:
            tag = receivedJson['tag']
            cipher.verify(base64.b64decode(tag))
        decodedPack = decryptedPack.decode("utf-8")
        replacedPack = decodedPack.replace('\x0f', '').replace(decodedPack[decodedPack.rindex('}')+1:], '')
        loadedJsonPack = simplejson.loads(replacedPack)  
        return loadedJsonPack

    def GetDeviceKey(self):
        _LOGGER.info('Retrieving HVAC encryption key')
        GENERIC_GREE_DEVICE_KEY = "a3K8Bx%2r8Y7#xDh"
        cipher = AES.new(GENERIC_GREE_DEVICE_KEY.encode("utf8"), AES.MODE_ECB)
        pack = base64.b64encode(cipher.encrypt(self.Pad('{"mac":"' + str(self._mac_addr) + '","t":"bind","uid":0}').encode("utf8"))).decode('utf-8')
        jsonPayloadToSend = '{"cid": "app","i": 1,"pack": "' + pack + '","t":"pack","tcid":"' + str(self._mac_addr) + '","uid": 0}'
        try:
            self._encryption_key = self.FetchResult(cipher, self._ip_addr, self._port, self._timeout, jsonPayloadToSend)['key'].encode("utf8")
        except:
            _LOGGER.error('Error getting device encryption key!')
            self._device_online = False
            self._online_attempts = 0
            return False
        else:
            _LOGGER.info('Fetched device encrytion key: %s' % str(self._encryption_key))
            self.CIPHER = AES.new(self._encryption_key, AES.MODE_ECB)
            self._device_online = True
            self._online_attempts = 0
            return True
        
    def GetGCMCipher(self, key):
        cipher = AES.new(key, AES.MODE_GCM, nonce=GCM_IV)
        cipher.update(GCM_ADD)
        return cipher

    def EncryptGCM(self, key, plaintext):
        encrypted_data, tag = self.GetGCMCipher(key).encrypt_and_digest(plaintext.encode("utf8"))
        pack = base64.b64encode(encrypted_data).decode('utf-8')
        tag = base64.b64encode(tag).decode('utf-8')
        return (pack, tag)

    def GetDeviceKeyGCM(self):
        _LOGGER.info('Retrieving HVAC encryption key')
        GENERIC_GREE_DEVICE_KEY = b'{yxAHAY_Lm6pbC/<'
        plaintext = '{"cid":"' + str(self._mac_addr) + '", "mac":"' + str(self._mac_addr) + '","t":"bind","uid":0}'
        pack, tag = self.EncryptGCM(GENERIC_GREE_DEVICE_KEY, plaintext)
        jsonPayloadToSend = '{"cid": "app","i": 1,"pack": "' + pack + '","t":"pack","tcid":"' + str(self._mac_addr) + '","uid": 0, "tag" : "' + tag + '"}'
        try:
            self._encryption_key = self.FetchResult(self.GetGCMCipher(GENERIC_GREE_DEVICE_KEY), self._ip_addr, self._port, self._timeout, jsonPayloadToSend)['key'].encode("utf8")
        except:
            _LOGGER.error('Error getting device encryption key!')
            self._device_online = False
            self._online_attempts = 0
            return False
        else:
            _LOGGER.info('Fetched device encrytion key: %s' % str(self._encryption_key))
            self._device_online = True
            self._online_attempts = 0
            return True

    def GreeGetValues(self, propertyNames):
        """Get values from AC with proper formatting based on debug logs."""
        plaintext = '{"cols":' + simplejson.dumps(propertyNames) + ',"mac":"' + str(self._mac_addr) + '","t":"status"}'
        
        if self.encryption_version == 1:
            cipher = self.CIPHER
            jsonPayloadToSend = '{"cid":"app","i":0,"pack":"' + base64.b64encode(cipher.encrypt(self.Pad(plaintext).encode("utf8"))).decode('utf-8') + '","t":"pack","tcid":"' + str(self._mac_addr) + '","uid":{}'.format(self._uid) + '}'
        elif self.encryption_version == 2:
            pack, tag = self.EncryptGCM(self._encryption_key, plaintext)
            jsonPayloadToSend = '{"cid":"app","i":0,"pack":"' + pack + '","t":"pack","tcid":"' + str(self._mac_addr) + '","uid":{}'.format(self._uid) + ',"tag" : "' + tag + '"}'
            cipher = self.GetGCMCipher(self._encryption_key)
        
        _LOGGER.debug('Raw request being sent to AC:')
        _LOGGER.debug('Plaintext request: %s', plaintext)
        _LOGGER.debug('Encrypted payload: %s', jsonPayloadToSend)
        
        response = self.FetchResult(cipher, self._ip_addr, self._port, self._timeout, jsonPayloadToSend)
        
        _LOGGER.debug('Raw response from AC:')
        _LOGGER.debug('Full response: %s', response)
        
        if 'dat' in response:
            _LOGGER.debug('Response dat array: %s', response['dat'])
            return response['dat']
        elif 'p' in response:
            _LOGGER.debug('Response p array: %s', response['p'])
            return response['p']
            
        return None

    def SetAcOptions(self, acOptions, newOptionsToOverride, optionValuesToOverride = None):
        if not (optionValuesToOverride is None):
            _LOGGER.debug('Setting acOptions with retrieved HVAC values')
            _LOGGER.debug('Raw options to override: ' + str(newOptionsToOverride))
            _LOGGER.debug('Raw option values: ' + str(optionValuesToOverride))
            
            # Only set options that have actual values
            if isinstance(newOptionsToOverride, list) and isinstance(optionValuesToOverride, list):
                for idx, key in enumerate(newOptionsToOverride):
                    if idx < len(optionValuesToOverride):
                        _LOGGER.debug('Setting %s: %s' % (key, optionValuesToOverride[idx]))
                        acOptions[key] = optionValuesToOverride[idx]
                    else:
                        _LOGGER.debug('Skipping option without value: %s' % key)
            _LOGGER.debug('Done setting acOptions')
        else:
            _LOGGER.debug('Overwriting acOptions with new settings')
            for key, value in newOptionsToOverride.items():
                _LOGGER.debug('Overwriting %s: %s' % (key, value))
                acOptions[key] = value
            _LOGGER.debug('Done overwriting acOptions')
        return acOptions
        
    def SendStateToAc(self, timeout):
        """Send state to AC with proper status checking and command formatting."""
        try:
            # Format the command based on the debug logs format
            cmd = {
                "t": "cmd",
                "opt": [],
                "p": [],
                "sub": self._mac_addr
            }
            
            # Add changed parameters to cmd
            for key, value in self._acOptions.items():
                if value is not None:
                    cmd["opt"].append(key)
                    cmd["p"].append(value)
            
            if not cmd["opt"]:
                return
                
            statePackJson = simplejson.dumps(cmd)
            _LOGGER.debug('Sending state pack to AC: %s', statePackJson)

            if self.encryption_version == 1:
                cipher = self.CIPHER
                sentJsonPayload = '{"cid":"app","i":0,"pack":"' + base64.b64encode(cipher.encrypt(self.Pad(statePackJson).encode("utf8"))).decode('utf-8') + '","t":"pack","tcid":"' + str(self._mac_addr) + '","uid":{}'.format(self._uid) + '}'
            elif self.encryption_version == 2:
                pack, tag = self.EncryptGCM(self._encryption_key, statePackJson)
                sentJsonPayload = '{"cid":"app","i":0,"pack":"' + pack + '","t":"pack","tcid":"' + str(self._mac_addr) + '","uid":{}'.format(self._uid) + ',"tag":"' + tag +'"}'
                cipher = self.GetGCMCipher(self._encryption_key)
            
            _LOGGER.debug('Raw state pack to send: ' + statePackJson)
            _LOGGER.debug('Raw encrypted payload to send: ' + sentJsonPayload)
        
            receivedJsonPayload = self.FetchResult(cipher, self._ip_addr, self._port, timeout, sentJsonPayload)
            _LOGGER.debug('Raw response from HVAC: ' + str(receivedJsonPayload))
            
            return receivedJsonPayload.get('r') == 200
            
        except Exception as e:
            _LOGGER.error('Error sending command to AC: %s', str(e))
            raise


    def UpdateHATargetTemperature(self):
        """Update the target temperature value with proper error checking."""
        try:
            if not self._is_main_unit and self._acOptions is not None and 'StTem' in self._acOptions:
                # Add MIN_TEMP to the temperature reported by the AC
                self._target_temperature = self._acOptions['StTem'] + MIN_TEMP
                if self._target_temp_entity_id:
                    target_temp_state = self.hass.states.get(self._target_temp_entity_id)
                    if target_temp_state:
                        attr = target_temp_state.attributes
                        # Validate the transformed temperature is within range
                        if MIN_TEMP <= self._target_temperature <= MAX_TEMP:
                            self.hass.states.async_set(
                                self._target_temp_entity_id, 
                                float(self._target_temperature), 
                                attr
                            )
                _LOGGER.debug('HA target temp set according to HVAC state (after offset) to: %s', 
                            self._target_temperature)
        except Exception as e:
            _LOGGER.error('Error updating target temperature: %s', str(e))

    def UpdateHAOptions(self):
        """Update HA options with proper error checking."""
        try:
            if self._acOptions is not None and 'EnSvSt' in self._acOptions:
                if (self._acOptions['EnSvSt'] == 1):
                    self._current_powersave = STATE_ON
                elif (self._acOptions['EnSvSt'] == 0):
                    self._current_powersave = STATE_OFF
                else:
                    self._current_powersave = STATE_UNKNOWN
                    
                if self._powersave_entity_id:
                    powersave_state = self.hass.states.get(self._powersave_entity_id)
                    if powersave_state:
                        attr = powersave_state.attributes
                        if self._current_powersave in (STATE_ON, STATE_OFF):
                            self.hass.states.async_set(self._powersave_entity_id, self._current_powersave, attr)
                            
                _LOGGER.debug('HA powersave option set according to HVAC state to: %s', self._current_powersave)
        except Exception as e:
            _LOGGER.error('Error updating HA options: %s', str(e))

    def UpdateHAHvacMode(self):
        """Update HVAC mode with proper error checking."""
        try:
            if self._acOptions is not None and 'Pow' in self._acOptions:
                if (self._acOptions['Pow'] == 0):
                    self._hvac_mode = HVACMode.OFF
                elif 'Mod' in self._acOptions and self._acOptions['Mod'] < len(self._hvac_modes):
                    self._hvac_mode = self._hvac_modes[self._acOptions['Mod']]
                else:
                    self._hvac_mode = HVACMode.OFF
                _LOGGER.debug('HA operation mode set according to HVAC state to: %s', self._hvac_mode)
        except Exception as e:
            _LOGGER.error('Error updating HVAC mode: %s', str(e))

    def UpdateHAFanMode(self):
        """Update fan mode with proper error checking."""
        try:
            if not self._is_main_unit or self._fan_modes is None:
                return
                
            if self._acOptions is not None:
                quier = self._acOptions.get('Quier', 0)
                wdspd = self._acOptions.get('WdSpd', 0)
                
                if quier and int(quier) >= 1:
                    self._fan_mode = 'Quiet'
                elif wdspd is not None:
                    try:
                        if 0 <= int(wdspd) < len(self._fan_modes):
                            self._fan_mode = self._fan_modes[int(wdspd)]
                        else:
                            self._fan_mode = self._fan_modes[0]
                    except (IndexError, ValueError):
                        _LOGGER.warning(f"Invalid fan speed index: {wdspd}")
                        self._fan_mode = self._fan_modes[0]
                else:
                    self._fan_mode = self._fan_modes[0]
                    
                _LOGGER.debug('HA fan mode set according to HVAC state to: %s', self._fan_mode)
        except Exception as e:
            _LOGGER.error('Error updating fan mode: %s', str(e))

    def UpdateHACurrentTemperature(self):
        """Update current temperature with proper error checking."""
        try:
            if not self._is_main_unit and not self._temp_sensor_entity_id:
                if self._has_temp_sensor and self._acOptions is not None and 'TemSen' in self._acOptions:
                    raw_temp = self._acOptions['TemSen']
                    self._current_temperature = self.hass.config.units.temperature(
                        float(raw_temp + MIN_TEMP), 
                        self.unit_of_measurement
                    )
                    _LOGGER.debug('HA current temperature set with device built-in temperature sensor state (after offset): %s', 
                                self._current_temperature)
        except Exception as e:
            _LOGGER.error('Error updating current temperature: %s', str(e))

    def UpdateHAStateToCurrentACState(self):
        """Update all HA state properties based on current AC state with proper error handling"""
        try:
            self.UpdateHATargetTemperature()
            self.UpdateHAOptions()
            self.UpdateHAHvacMode()                           
            self.UpdateHAFanMode()
            self.UpdateHACurrentTemperature()
        except Exception as e:
            _LOGGER.error(f"Error updating HA state: {str(e)}")
            

    def SyncState(self, acOptions = {}):

        """Sync state with improved error handling and logging"""
        try:
            _LOGGER.debug('Starting SyncState')
            _LOGGER.debug('Current AC Options: %s', self._acOptions)
            
            # Validate connection and encryption
            if not self._encryption_key:
                _LOGGER.error("No encryption key available")
                return None
                
            # Fetch current values with timeout handling
            try:
                currentValues = self.GreeGetValues(self._optionsToFetch)
                _LOGGER.debug('Raw current values response: %s', currentValues)
            except socket.timeout:
                _LOGGER.error("Timeout while fetching device values")
                self._handle_connection_failure()
                return None
            except Exception as e:
                _LOGGER.error('Error fetching device values: %s', str(e))
                self._handle_connection_failure()
                return None
                
            # Update device state
            if not self._disable_available_check:
                if not self._device_online:
                    self._device_online = True
                    self._online_attempts = 0
                    
            # Set latest status from device
            self._acOptions = self.SetAcOptions(self._acOptions, self._optionsToFetch, currentValues)
            _LOGGER.debug('Updated AC Options after fetch: %s', self._acOptions)
            
            # Apply any new options
            if acOptions:
                self._acOptions = self.SetAcOptions(self._acOptions, acOptions)
                _LOGGER.debug('Final AC Options after overwrite: %s', self._acOptions)
                
            # Send updates if needed
            if not self._firstTimeRun and acOptions:
                self.SendStateToAc(self._timeout)
            else:
                self._firstTimeRun = False
                self._LogCurrentState()
                
            # Update HA state
            self.UpdateHAStateToCurrentACState()
            
            _LOGGER.debug('Finished SyncState')
            return True
            
        except Exception as e:
            _LOGGER.error(f"Error in SyncState: {str(e)}")
            return None
            
    def _handle_connection_failure(self):
        """Handle connection failures consistently"""
        if not self._disable_available_check:
            self._online_attempts += 1
            if self._online_attempts >= self._max_online_attempts:
                _LOGGER.debug('Device unreachable after %s attempts. Marking as offline.', 
                            self._max_online_attempts)
                self._device_online = False
                self._online_attempts = 0
                
    def _LogCurrentState(self):
        """Log the current state of the device"""
        _LOGGER.debug('Current Device State:')
        _LOGGER.debug('Device Name: %s', self._name)
        _LOGGER.debug('IP Address: %s', self._ip_addr)
        _LOGGER.debug('MAC Address: %s', self._mac_addr)
        _LOGGER.debug('Target Temperature: %s', self._target_temperature)
        _LOGGER.debug('Current Temperature: %s', self._current_temperature)
        _LOGGER.debug('HVAC Mode: %s', self._hvac_mode)
        _LOGGER.debug('Fan Mode: %s', self._fan_mode)
        _LOGGER.debug('Has Temperature Sensor: %s', self._has_temp_sensor)
        _LOGGER.debug('Current Options: %s', self._acOptions)

    async def _async_temp_sensor_changed(self, event: Event[EventStateChangedData]) -> None:
        entity_id = event.data["entity_id"]
        old_state = event.data["old_state"]
        new_state = event.data["new_state"]
        s = str(old_state.state) if hasattr(old_state,'state') else "None"
        _LOGGER.debug('temp_sensor state changed | ' + str(entity_id) + ' from ' + s + ' to ' + str(new_state.state))
        # Handle temperature changes.
        if new_state is None:
            return
        self._async_update_current_temp(new_state)
        return self.schedule_update_ha_state(True)
        
    @callback
    def _async_update_current_temp(self, state):
        _LOGGER.debug('Thermostat updated with changed temp_sensor state | ' + str(state.state))
        unit = state.attributes.get(ATTR_UNIT_OF_MEASUREMENT)
        try:
            _state = state.state
            _LOGGER.debug('Current state temp_sensor: ' + _state)
            if self.represents_float(_state):
                self._current_temperature = self.hass.config.units.temperature(
                    float(_state), unit)
                _LOGGER.debug('Current temp: ' + str(self._current_temperature))
        except ValueError as ex:
            _LOGGER.error('Unable to update from temp_sensor: %s' % ex)

    def represents_float(self, s):
        _LOGGER.debug('temp_sensor state represents_float |' + str(s))
        try: 
            float(s)
            return True
        except ValueError:
            return False     

    @callback

    async def _async_powersave_entity_state_changed(self, event: Event[EventStateChangedData]) -> None:
        entity_id = event.data["entity_id"]
        old_state = event.data["old_state"]
        new_state = event.data["new_state"]
        _LOGGER.debug('powersave_entity state changed | ' + str(entity_id) + ' from ' + (str(old_state.state) if hasattr(old_state,'state') else "None") + ' to ' + str(new_state.state))
        if new_state is None:
            return
        if new_state.state is "off" and (old_state is None or old_state.state is None):
            _LOGGER.debug('powersave_entity state changed to off, but old state is None. Ignoring to avoid beeps.')
            return
        if new_state.state is self._current_powersave:
            # do nothing if state change is triggered due to Sync with HVAC
            return
        if not hasattr(self, "_hvac_mode"):
            _LOGGER.debug('Cant set powersave in unknown mode')
            return
        if self._hvac_mode is None:
            _LOGGER.debug('Cant set powersave in unknown HVAC mode (self._hvac_mode is None)')
            return
        if not self._hvac_mode in (HVACMode.COOL):
            # do nothing if not in cool mode
            _LOGGER.debug('Cant set powersave in %s mode' % str(self._hvac_mode))
            return
        self._async_update_current_powersave(new_state)
        return self.schedule_update_ha_state(True)

    @callback
    def _async_update_current_powersave(self, state):
        _LOGGER.debug('Udating HVAC with changed powersave_entity state | ' + str(state.state))
        if state.state is STATE_ON:
            self.SyncState({'EnSvSt': 1})
            return
        elif state.state is STATE_OFF:
            self.SyncState({'EnSvSt': 0})
            return
        _LOGGER.error('Unable to update from powersave_entity!')

    def _async_target_temp_entity_state_changed(self, event: Event[EventStateChangedData]) -> None:
        entity_id = event.data["entity_id"]
        old_state = event.data["old_state"]
        new_state = event.data["new_state"]
        _LOGGER.debug('target_temp_entity state changed | ' + str(entity_id) + ' from ' + (str(old_state.state) if hasattr(old_state,'state') else "None") + ' to ' + str(new_state.state))
        if new_state is None:
            return
        if new_state.state is "off" and (old_state is None or old_state.state is None):
            _LOGGER.debug('target_temp_entity state changed to off, but old state is None. Ignoring to avoid beeps.')
            return
        if int(float(new_state.state)) is self._target_temperature:
            # do nothing if state change is triggered due to Sync with HVAC
            return
        self._async_update_current_target_temp(new_state)
        return self.schedule_update_ha_state(True)

    @callback
    def _async_update_current_target_temp(self, state):
        s = int(float(state.state))
        _LOGGER.debug('Updating HVAC with changed target_temp_entity state | ' + str(s))
        if (s >= MIN_TEMP) and (s <= MAX_TEMP):
            self.SyncState({'StTem': s})
            return
        _LOGGER.error('Unable to update from target_temp_entity!')

    @property
    def should_poll(self):
        _LOGGER.debug('should_poll()')
        # Return the polling state.
        return True

    @property
    def available(self):
        if self._disable_available_check:
            return True
        else:
            if self._device_online:
                _LOGGER.debug('available(): Device is online')
                return True
            else:
                _LOGGER.debug('available(): Device is offline')
                return False

    def update(self):
        """Update the device's state."""
        _LOGGER.debug('update()')
        # Since encryption key is shared, we only need to sync state
        if self._encryption_key:
            self.SyncState()
        else:
            _LOGGER.error('No encryption key available')

    @property
    def name(self):
        _LOGGER.debug('name(): ' + str(self._name))
        # Return the name of the climate device.
        return self._name

    @property
    def temperature_unit(self):
        """Return the unit of measurement."""
        return self._temperature_unit

    @property
    def current_temperature(self):
        _LOGGER.debug('current_temperature(): ' + str(self._current_temperature))
        # Return the current temperature.
        return self._current_temperature

    @property
    def min_temp(self):
        """Return the minimum temperature."""
        _LOGGER.debug('min_temp(): %s', MIN_TEMP)
        return MIN_TEMP
        
    @property
    def max_temp(self):
        """Return the maximum temperature."""
        _LOGGER.debug('max_temp(): %s', MAX_TEMP)
        return MAX_TEMP
        
    @property
    def target_temperature(self):
        """Return the temperature we try to reach (with offset)."""
        _LOGGER.debug('target_temperature(): %s', self._target_temperature)
        return self._target_temperature
        
    @property
    def target_temperature_step(self):
        _LOGGER.debug('target_temperature_step(): ' + str(self._target_temperature_step))
        # Return the supported step of target temperature.
        return self._target_temperature_step

    @property
    def hvac_mode(self):
        _LOGGER.debug('hvac_mode(): ' + str(self._hvac_mode))
        # Return current operation mode ie. heat, cool, idle.
        return self._hvac_mode

    @property
    def hvac_modes(self):
        _LOGGER.debug('hvac_modes(): ' + str(self._hvac_modes))
        # Return the list of available operation modes.
        return self._hvac_modes

    @property
    def fan_mode(self):
        _LOGGER.debug('fan_mode(): ' + str(self._fan_mode))
        # Return the fan mode.
        return self._fan_mode

    @property
    def fan_modes(self):
        _LOGGER.debug('fan_list(): ' + str(self._fan_modes))
        # Return the list of available fan modes.
        return self._fan_modes
        
    @property
    def supported_features(self):
        """Return the list of supported features based on unit type"""
        try:
            supported = 0
            
            # Basic features for all units
            supported |= ClimateEntityFeature.TURN_ON
            supported |= ClimateEntityFeature.TURN_OFF
            
            # Temperature control only for secondary units
            if not self._is_main_unit:
                supported |= ClimateEntityFeature.TARGET_TEMPERATURE
                
            # Fan control only for main unit
            if self._is_main_unit and hasattr(self, '_fan_modes') and self._fan_modes:
                supported |= ClimateEntityFeature.FAN_MODE
            
            # Log supported features
            feature_list = []
            if supported & ClimateEntityFeature.TARGET_TEMPERATURE:
                feature_list.append(("TARGET_TEMPERATURE", ClimateEntityFeature.TARGET_TEMPERATURE))
            if supported & ClimateEntityFeature.FAN_MODE:
                feature_list.append(("FAN_MODE", ClimateEntityFeature.FAN_MODE))
            if supported & ClimateEntityFeature.TURN_ON:
                feature_list.append(("TURN_ON", ClimateEntityFeature.TURN_ON))
            if supported & ClimateEntityFeature.TURN_OFF:
                feature_list.append(("TURN_OFF", ClimateEntityFeature.TURN_OFF))
                
            _LOGGER.debug(f'Supported features for {self._name} (Main unit: {self._is_main_unit}):')
            for feature_name, feature_value in feature_list:
                _LOGGER.debug(f'- {feature_name}: {feature_value}')
            _LOGGER.debug(f'Total supported_features(): {supported}')
            
            return supported
            
        except Exception as e:
            _LOGGER.error(f"Error determining supported features: {str(e)}")
            return ClimateEntityFeature.TURN_ON | ClimateEntityFeature.TURN_OFF

    @property
    def unique_id(self):
        # Return unique_id
        return self._unique_id

    def set_temperature(self, **kwargs):
        """Set new target temperature only for secondary units."""
        if self._is_main_unit:
            _LOGGER.debug('Temperature control not available on main unit')
            return
            
        _LOGGER.debug('set_temperature(): %s', kwargs.get(ATTR_TEMPERATURE))
        
        if kwargs.get(ATTR_TEMPERATURE) is not None and self._acOptions['Pow'] != 0:
            ac_temp = int(kwargs.get(ATTR_TEMPERATURE) - MIN_TEMP)
            _LOGGER.debug('SyncState with StTem=%s (after removing offset)', ac_temp)
            self.SyncState({'StTem': ac_temp})
            self.schedule_update_ha_state()

    def set_fan_mode(self, fan):
        """Set fan mode only for main unit."""
        if not self._is_main_unit:
            _LOGGER.debug('Fan control not available on secondary units')
            return
            
        _LOGGER.debug('set_fan_mode(): ' + str(fan))
        if not (self._acOptions['Pow'] == 0):
            if (fan.lower() == 'quiet'):
                self.SyncState({'WdsPd': 0, 'Quier': 1})
            else:
                self.SyncState({'WdSpd': self._fan_modes.index(fan), 'Quier': 0})
            self.schedule_update_ha_state()

    def set_hvac_mode(self, hvac_mode):
        """Set HVAC mode with improved error handling and state validation"""
        try:
            _LOGGER.debug('set_hvac_mode(): ' + str(hvac_mode))
            
            if not hasattr(self, '_acOptions'):
                _LOGGER.error("Device state not initialized")
                return
                
            c = {}
            if hvac_mode == HVACMode.OFF:
                # Simply set power to off, don't change mode
                c.update({'Pow': 0})
            else:
                # For any other mode, turn on and set the mode
                if hvac_mode not in self._hvac_modes:
                    _LOGGER.error(f"Invalid HVAC mode: {hvac_mode}")
                    return
                    
                c.update({
                    'Pow': 1,
                    'Mod': self._hvac_modes.index(hvac_mode)
                })
                        
            self.SyncState(c)
            self.schedule_update_ha_state()
            
        except Exception as e:
            _LOGGER.error(f"Error setting HVAC mode: {str(e)}")

    def turn_on(self): 
        _LOGGER.debug('turn_on(): ')
        # Turn on.
        c = {'Pow': 1}
        self.SyncState(c)
        self.schedule_update_ha_state()

    def turn_off(self):
        _LOGGER.debug('turn_off(): ')
        # Turn off.
        c = {'Pow': 0}
        self.SyncState(c)
        self.schedule_update_ha_state()

    async def async_added_to_hass(self):
        _LOGGER.debug('Gree climate device added to hass()')
        self.update()
