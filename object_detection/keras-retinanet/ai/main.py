import keras
from keras_retinanet import models
from keras_retinanet.utils.image import read_image_bgr, preprocess_image, resize_image
from keras_retinanet.utils.visualization import draw_box, draw_caption
from keras_retinanet.utils.colors import label_color
import tensorflow as tf

import cv2
import numpy as np
np.set_printoptions(linewidth=500) # For map debugging (view map array in terminal)
from fastgrab._linux_x11 import screenshot
import pyautogui as pag
import time
import threading
import sys
import matplotlib.pyplot as plt

# Custom imports
from mapper import live_map
from auto_controller import controller


# Dummy function, does nothing
def nothing(x):
    pass


# Some keras/tensorflow related stuff, even I'm not entirely sure what it does exactly
def get_session():
    config = tf.ConfigProto()
    config.gpu_options.allow_growth = True
    return tf.Session(config=config)


# Initializes model for detection, mapper, controller and finds game window
def initialise(game_window, game_width, game_height, model_path):
    keras.backend.tensorflow_backend.set_session(get_session())
    model = models.load_model(model_path, backbone_name='resnet101')

    # Setting up windows
    cv2.namedWindow("Map", cv2.WINDOW_NORMAL)
    cv2.resizeWindow("Map", 720, 480)
    cv2.namedWindow("Screen")
    cv2.moveWindow("Screen", 1000, 0)
    cv2.createTrackbar("ScoreThresh", "Screen", 70, 99, nothing)

    # Finding game window using included .png
    window_x, window_y, temp1, temp2 = pag.locateOnScreen("find_game_window.png")

    # Adding a 20 pixel offset to the y coordinate since the function above returns the x,y
    # coordinates of the menu bar - we want the coords of the gameplay below this bar
    window_y += 20

    # Setup controller
    ctrl = controller(window_x, window_y)
    
    # Get padding for converting 720:480 aspect ratio to 1:1
    temp3, padding = get_screen(game_window, window_x, window_y)
    
    # Initialising mapper object with retroarch pid and memory addresses to watch for player's
    # x and y coordinates
    mp = live_map(game_width, game_height, padding, 4681, 0x55c106d0bf5c, 0x55c106d0bf5e)

    return ctrl, window_x, window_y, model, mp


# Gets single frame of gameplay as a numpy array on which object inference will be later ran
def get_screen(game_window, window_x, window_y):
    # Getting game screen as input
    screenshot(window_x, window_y, game_window)
    frame = game_window[:, :, :3] # Splicing off alpha channel

    # Making input a square by padding
    padding = 0
    if game_height < game_width:
        padding = int((game_width - game_height) / 2)
        frame = cv2.copyMakeBorder(frame, padding, padding, 0, 0, cv2.BORDER_CONSTANT, (0, 0, 0))
    elif game_height > game_width:
        padding = int((game_width - game_width) / 2)
        frame = cv2.copyMakeBorder(frame, 0, 0, padding, padding, cv2.BORDER_CONSTANT, (0, 0, 0))
    
    return frame, padding


# Runs inference on a single input frame and returns detected bounding boxes
def run_detection(frame, model, labels_to_names, mp):
    # Get trackbar value for confidence score threshold
    score_thresh = cv2.getTrackbarPos("ScoreThresh", "Screen") 

    # Process image and run inference
    image = preprocess_image(frame) # Retinanet specific preprocessing
    image, scale = resize_image(image, min_side = 400) # This model was trianed with 400p images
    boxes, scores, labels = model.predict_on_batch(np.expand_dims(image, axis=0)) # Run inference
    boxes /= scale # Ensures bounding boxes are of the correct scale

    # Visualize detections from inferencing
    predictions_for_map = []
    for box, score, label in zip(boxes[0], scores[0], labels[0]):
        # We can break here because the bounding boxes are in descending order in terms of confidence
        if score < (score_thresh / 100):
            break
        
        # Skipping NPC detections
        if (label == 2):
            continue

        # Appending to output array
        predictions_for_map.append((label, box))

        # Drawing labels and bounding boxes on input frame
        color = label_color(label)
        b = box.astype(int)
        draw_box(frame, b, color=color)
        caption = "{} {:.2f}".format(labels_to_names[label], score)
        draw_caption(frame, b, caption)
    
    # Show output frame with detections
    cv2.imshow("Screen", frame)
    status = "ok"
    # Press 'q' to quit safely
    if cv2.waitKey(1) == ord('q'):
        status = "quit"

    return status, predictions_for_map, False

# Main function
if __name__ == "__main__":
    # Setup variables here
    game_width = 720
    game_height = 480
    game_window = np.zeros((game_height, game_width, 4), "uint8")
    model_path = "../inference_graphs/400p/resnet101_csv_13.h5" # Model to be used for detection
    labels_to_names = {0: "pokecen", 1: "pokemart", 2: "npc", 3: "house", 4: "gym", 5: "exit"} # Labels to draw

    # Initialising model, window, controller, and mapper
    ctrl, window_x, window_y, model, mp = initialise(game_window, game_width, game_height, model_path)

    is_init_frame = True
    predictions_for_map = []
    temp_bool = None
    key_pressed = None
    map_grid = np.full((2, 2), 255, dtype=np.uint8)
    four_frame_count = 0

    actions = [] # Use to set pre-defined actions to send to controller (default is random)
    action_index = -1 # Initialise this from -1
    
    # It takes about 5 frames for our player characte to perform a movement in any direction. Thus,
    # it makes no sense to update the map during each of these frames, especially because the character
    # will be stuck between two tiles in some frames and this will throw off our mapping algorithm
    while True:  
        # 0th frame handles key presses
        if (four_frame_count == 0):
            # time.sleep(0.5) # Adjust this to reduce frequency of actions sent by controller
            
            # Used to iterate through pre-defined actions and break once actions have ended
            #action_index += 1
            #if (action_index >= len(actions)):
                #break

            # Initial startup frame to put detection and key presses in sync
            if (is_init_frame == True):
                key_pressed = None
                frame, temp = get_screen(game_window, window_x, window_y)
                status, predictions_for_map, temp_init = run_detection(frame, model, labels_to_names, mp)
                four_frame_count += 1
                map_grid = mp.draw_map(key_pressed, predictions_for_map)
                cv2.imshow("Map", map_grid)

            # All other frames
            else:
                key_pressed = ctrl.random_movement()#action=actions[action_index]) # Use action parameter for pre-defined input
            
            print(key_pressed) # For debugging purposes TODO: Display pressed_key in "Screen" window
            four_frame_count += 1

        # All other frames just deal with normal inferencing for nicer visualization purposes, but this does
        # nothing to affect out mapping algorithm
        elif (four_frame_count < 4):
            frame, temp = get_screen(game_window, window_x, window_y)
            status, predictions_for_map, temp_bool = run_detection(frame, model, labels_to_names, mp)
            four_frame_count += 1

            if (status == "quit"):
                break

        # Last frame is when the new detections are properly taken from the inferencing, and are used as inputs in the
        # mapping algorithm
        elif (four_frame_count == 4):
            frame, temp = get_screen(game_window, window_x, window_y)
            status, predictions_for_map, temp_bool = run_detection(frame, model, labels_to_names, mp)

            # Draw map in window
            # Take note that there is a one frame delay because of something in OpenCV itself. If you print
            # the map_grid, you'll see that the mapping is actually performed realtime
            map_grid = mp.draw_map(key_pressed, predictions_for_map)
            cv2.imshow("Map", map_grid)
            
            # Reset 5 frame cycle
            four_frame_count = 0

            if (status == "quit"):
                break

        # Init frame is over, change flag accordingly
        if (is_init_frame == True):
            is_init_frame = temp_bool      

    # Clean running processes and close program cleanly
    cv2.destroyAllWindows()
    sys.exit()