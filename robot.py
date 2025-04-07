#############################
##### Raider Robot Code #####
#############################

"""

Connect to controller using bluetooth

Use GPIO pins for
12: Left  motor PWM
19: Right motor PWM

PWM Input Pulse (high time)
1-2 ms nominal

PWM Input Rate (period)
2.9 - 100 ms

Backwards: 1.0 ms =  50000
Neutral:   1.5 ms =  75000
Forwards:  2.0 ms = 100000

PWM == Pulse With Modulation

"""

################################
##### python libary import #####
################################

import sys
import time
from math import dist, atan2, sin, cos, pi
from select import select

# Append system path so that evdev can be imported
sys.path.append('/home/pi/.local/lib/python3.9/site-packages')

# handles bluetooth
from evdev import list_devices, InputDevice, categorize, ecodes, ff
# handles motors
import pigpio
# pigpio shortcut
pwm = pigpio.pi()
# handles takle sensers
import RPi.GPIO as GPIO

# prints out date and time
#   %a = day of week, %d = day of month, %b = month, %Y = year, %H:%M:%S = hour:minute:second
print(time.strftime("%a, %d %b %Y %H:%M:%S", time.localtime()))

#####################
##### Constants #####
#####################


MOTORS_ENABLED = True

# min value for joystick activation
DEAD_ZONE = 0.15

# PMW frequency 
PULSE_MIN = 1000
PULSE_MAX = 2000

############################
##### Global Variables #####
############################


# Empty var for future paired controler
paired_controler = None

##############################
##### Main Function Call #####
##############################

if __name__ == "__main__":
    main()


##################################
##### Motor and Sensor Setup #####
##################################

def motor_setup():
    print("Motor SetUp Started")
    # pins for motors
    right_motor_pin = 19
    left_motor_pin = 13
    track_motor_pin = 21

    # sets motors mode
    pwm.set_mode(right_motor_pin, pigpio.OUTPUT)
    pwm.set_mode(left_motor_pin, pigpio.OUTPUT)
    pwm.set_mode(track_motor_pin, pigpio.OUTPUT)

    # confirms motors are ready
    print("Motors Ready")

def tackle_senor_setup():
    print("Tackle Senor SetUp Started")
    # pin for senor
    tackle_senor_pin = 14

    # sets up senor
    GPIO.setmode(GPIO.BCM)
    GPIO.setup(tackle_senor_pin, GPIO.IN)

    # confirms sensor is ready
    print("Tackle Senor Ready")

#######################################
##### Bluetooth Device Connection #####
#######################################

# list of devices that can pair to the robot
pairable_devices = [
    "Xbox Wireless Controller",
    "Wireless Controller",                  # PS4
    "DualSense Wireless Controller",        # PS5 Dual Shock
    "Xbox 360 Wireless Receiver (XBOX)",
]

def pair_device():
    print("Searching for pairable device")
    controler = None
    
    # finds and sets device
    while controler == None:
        controler = find_device()
    
    # confirms what device is paired, and that it is paired
    print(controler + " connected")
    print(controler.capabilities(verbose=True))

    return controler

def find_device():
    # finds devices
    for device in list_devices:
        if InputDevice(device).name in pairable_devices:
            return device
    return None

##################################
##### Bluetooth Device Setup #####
##################################

# Controller constants

A     = ecodes.BTN_A
B     = ecodes.BTN_B
X     = ecodes.BTN_X
Y     = ecodes.BTN_Y
LB    = ecodes.BTN_TL
RB    = ecodes.BTN_TR
BACK  = ecodes.BTN_SELECT
START = ecodes.BTN_START
HOME  = ecodes.BTN_MODE

# controler vars
in_reverse = False
speed_scale = 0.3
input_event = None
joystick_x_pos = joystick_y_pos = 0
left_velocity = right_velocity = 0
left_acceleration = right_acceleration = 0

def specific_input_setup(device):
    global L_JOY_X, L_JOY_Y, R_JOY_X, R_JOY_Y, BACK, MIN, MAX

    match device.name:

        case "Xbox Wireless Controller":
            L_JOY_X    =   0
            L_JOY_Y    =   1
            R_JOY_X    =   2     # ABS_RZ
            R_JOY_Y    =   5     # ABS_Z
            BACK  = ecodes.KEY_BACK
            MIN = 0         # Joystick min
            MAX = 2**16-1   # Joystick max
    
        case "Wireless Controller" | "DualSense Wireless Controller":
            L_JOY_X    =   0
            L_JOY_Y    =   1
            R_JOY_X    =   3
            R_JOY_Y    =   4
            MIN = 0         # Joystick min
            MAX = 2**8-1    # Joystick max
        
    joystick_x_pos = joystick_y_pos = MAX/2


#########################
##### Event Handler #####
#########################

def read_event(event):
    event = event.code

    # if the home button is pressed the robot will shut off
    if event == HOME:
        raise Exception('Home Button Pressed')
    
    # checks if the reverse button is pressed
    if event == LB:
        in_reverse = True
    else:
        in_reverse = False
    
    # if the right joystick is moved the movement varubles are changed
    if event == R_JOY_X or event == R_JOY_Y:
        right_joystick_moved(R_JOY_Y, R_JOY_X, event.value)



def right_joystick_moved(joy_x, joy_y, event_value):

    # These if statements shift the range of the joystick
    # to [-1, 1]
    if joy_x:
        joystick_x_pos = event_value / MAX * 2 - 1
    
    if joy_y:
        joystick_y_pos = event_value / MAX * 2 - 1
    
    # if the value of the joystick is less then the 
    # DEAD_ZONE value, it turns it to 0
    if abs(joystick_x_pos) < DEAD_ZONE: joy_x = 0
    if abs(joystick_y_pos) < DEAD_ZONE: joy_y = 0

    # calculates reverse value
    rev = bool_to_int(in_reverse)

    # Finds angle of joystick for acceleration
    theta = atan2(joystick_x_pos, -joystick_y_pos * rev)
    
    # Radius of joystick from center, then clamps it to [0,1]
    # as the device is not perfect
    radius = dist((0,0), (joystick_x_pos, joystick_y_pos))
    radius = min(radius, 1)

    # Calculates Acceleration
    left_acceleration = -sin(theta) + cos(theta)
    right_acceleration = sin(theta) + cos(theta)

    # clamp these values to [-1, 1]
    left_acceleration = min(max(left_acceleration, -1), 1)
    right_acceleration = min(max(right_acceleration, -1), 1)

    # Scale these values by the radius
    left_acceleration *= radius
    right_acceleration *= radius

    # Round to edge values using the dead zone
    left_acceleration = 0 if abs(left_acceleration) < DEAD_ZONE else left_acceleration
    right_acceleration = 0 if abs(right_acceleration) < DEAD_ZONE else right_acceleration




def main():
    print("Starting SetUp")
    motor_setup()
    tackle_senor_setup()
    print("SetUp Finished")

    paired_controler = pair_device()
    specific_input_setup(paired_controler)

    print("Starting Input Loop")
    while True:
        input_loop()

def input_loop():
    read_list, write_list, exp_list = select([dev.fd], [], [], 0.0001)

    if read_list:
        for event in paired_controler.read():
            read_event(event)
    
    # change velocity to acceleration
    left_velocity = left_acceleration
    right_velocity = right_acceleration

    # clamp velocity to [-1, 1]
    left_velocity = min(max(left_velocity, -1), 1)
    right_velocity = min(max(right_velocity, -1), 1)

    # speed scale
    scale_min = 0.3

    # change in velcoity scale over time
    delta = 0.0001

    # Increase / Decrease speed scale based on position of joysitck
    if abs(left_acceleration) > 0.8 or abs(right_acceleration) > 0.8:
        scale += delta
    else:
        scale -= delta
    
    # Clamp scale to [0.3, 1]
    scale = min(max(scale, scale_min), 1)











def bool_to_int(foo):
    if foo:
        return 1
    return -1