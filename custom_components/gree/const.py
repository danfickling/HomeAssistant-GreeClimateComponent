DOMAIN = "gree"

CONF_HVAC_MODES = "hvac_modes"
CONF_ENCRYPTION_KEY = 'encryption_key'
CONF_UID = 'uid'
CONF_FAN_MODES = 'fan_modes'
CONF_SWING_MODES = 'swing_modes'
CONF_SWING_HORIZONTAL_MODES = 'swing_horizontal_modes'
CONF_ENCRYPTION_VERSION = 'encryption_version'
CONF_DISABLE_AVAILABLE_CHECK  = 'disable_available_check'
CONF_TEMP_SENSOR_OFFSET = 'temp_sensor_offset'
CONF_DUCTED_MULTIZONE = 'ducted_multizone'
CONF_DUCTED_ZONE_COUNT = 'ducted_zone_count'

DEFAULT_PORT = 7000
DEFAULT_DUCTED_ZONE_COUNT = 8
DEFAULT_TARGET_TEMP_STEP = 1

MIN_TEMP_C = 16
MAX_TEMP_C = 30

MIN_TEMP_F = 61
MAX_TEMP_F = 86

TEMSEN_OFFSET = 40

# HVAC modes - these come from Home Assistant and are standard
DEFAULT_HVAC_MODES = ["auto", "cool", "dry", "fan_only", "heat", "off"]

# Ducted VRF units use a different Mod value mapping than standard split ACs:
# Standard: 0=auto, 1=cool, 2=dry, 3=fan_only, 4=heat
# Ducted VRF: 0=auto, 1=cool, 2=heat, 3=dry, 4=fan_only
DUCTED_HVAC_MODES = ["auto", "cool", "heat", "dry", "fan_only", "off"]

DEFAULT_FAN_MODES = ["auto", "low", "medium_low", "medium", "medium_high", "high", "turbo", "quiet"]
DEFAULT_SWING_MODES = ["default", "swing_full", "fixed_upmost", "fixed_middle_up", "fixed_middle", "fixed_middle_low", "fixed_lowest", "swing_downmost", "swing_middle_low", "swing_middle", "swing_middle_up", "swing_upmost"]
DEFAULT_SWING_HORIZONTAL_MODES = ["default", "swing_full", "fixed_leftmost", "fixed_middle_left", "fixed_middle", "fixed_middle_right", "fixed_rightmost"]

# Keys that can be updated via the options flow
OPTION_KEYS = {
    CONF_HVAC_MODES,
    CONF_FAN_MODES,
    CONF_SWING_MODES,
    CONF_SWING_HORIZONTAL_MODES,
    CONF_DISABLE_AVAILABLE_CHECK,
    CONF_TEMP_SENSOR_OFFSET,
    CONF_DUCTED_MULTIZONE,
    CONF_DUCTED_ZONE_COUNT,
}

MODES_MAPPING = {
  "Mod" : {
    "auto" : 0,
    "cool" : 1,
    "dry" : 2,
    "fan_only" : 3,
    "heat" : 4
  },
  "WdSpd" : {
    "auto" : 0,
    "low" : 1,
    "medium_low" : 2,
    "medium" : 3,
    "medium_high" : 4,
    "high" : 5
  },
  "SwUpDn" : {
    "default" : 0,
    "swing_full" : 1,
    "fixed_upmost" : 2,
    "fixed_middle_up" : 3,
    "fixed_middle" : 4,
    "fixed_middle_low" : 5,
    "fixed_lowest" : 6,
    "swing_downmost" : 7,
    "swing_middle_low" : 8,
    "swing_middle" : 9,
    "swing_middle_up" : 10,
    "swing_upmost" : 11
  },
  "SwingLfRig" : {
    "default" : 0,
    "swing_full" : 1,
    "fixed_leftmost" : 2,
    "fixed_middle_left" : 3,
    "fixed_middle" : 4,
    "fixed_middle_right" : 5,
    "fixed_rightmost" : 6
  }
}