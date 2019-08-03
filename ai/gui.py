import tkinter as tk
from PIL import Image, ImageTk
import cv2
import numpy as np
import threading

#from standalone_backend import poke_ai

"""
Stuff to add to GUI. 
- Speed slider

- Status listbox which can be double-clicked to open image at that point in time
Possible statuses:
- Finding frontier: (Frontier location)
- Moving to frontier: (Actions required to move there)
- Move: Up, Down, Left Right:
- In battle: (Model output scores after this battle)
- 
- Collision, continuing movement to frontier 
- Frontier obstructed, finding new frontier (Frontier location)
- 


- Matplotlib graph to show the score for each move slowly converge


- Battle AI training status, without output weights
- Turn on/off DQNN training: self.pa.bat_ai.continue_training = False
- 

- Try to get custom running speed version to work

Data to show:
- Number of battles done: self.pa.bat_ai.num_episodes_completed
- Number of state/action pairs: len(self.pa.bat_ai.battle_data)
- Last prediction values: self.pa.bat_ai.action_predicted_rewards[0]
- Randomness amount: self.pa.bat_ai.epsilon

- Last action performed: self.pa.key_pressed
- Collision detected: self.pa.collision_type

"""

class gui:
    def __init__(self, window, window_title):
        self.window = window
        self.window.title(window_title)
        self.window.resizable(False, False)

        self.game_window_size = {"top": 0, "left": 0, "width": 720, "height": 480}
        self.model_path = "../object_detection/keras-retinanet/inference_graphs/map_detector.h5" # Model to be used for detection
        self.labels_to_names = {0: "pokecen", 1: "pokemart", 2: "npc", 3: "house", 4: "gym", 5: "exit"} # Labels to draw
        #self.pa = poke_ai(self.model_path, self.labels_to_names, self.game_window_size)
        self.video = cv2.VideoCapture(0)
        self.cur_map_grid = None
        self.map_num = 0

        self.legend_label = tk.Label(self.window, text="Map Legend", font=("Helvetica", 12))
        self.legend_label.grid(row=0, column=4, padx=5, pady=5)
        self.legend = tk.Canvas(self.window, width=300, height=375)
        self.legend.grid(row=1, column=4, rowspan=3, padx=5, pady=5, sticky="n")
        self.legend.create_rectangle(3, 3, 295, 375, fill="#FFFFFF", outline="#000000", width=2)
        # Agent
        self.legend.create_rectangle(15, 15, 45, 45, width=1, outline="#000000", fill="#1CA621")
        self.legend.create_text(55, 30, anchor="w", font=("Helvetica", 10), text="Agent")
        # Target Frontier
        self.legend.create_rectangle(15, 60, 45, 90, width=1, outline="#000000", fill="#FF00EA")
        self.legend.create_text(55, 75, anchor="w", font=("Helvetica", 10), text="Target Frontier")
        # Wall / Boundary
        self.legend.create_rectangle(15, 105, 45, 135, width=1, outline="#000000", fill="#696969")
        self.legend.create_text(55, 120, anchor="w", font=("Helvetica", 10), text="Boundary")
        # NPC
        self.legend.create_rectangle(15, 150, 45, 180, width=1, outline="#000000", fill="#F58742")
        self.legend.create_text(55, 165, anchor="w", font=("Helvetica", 10), text="NPC")
        # House
        self.legend.create_rectangle(15, 195, 45, 225, width=1, outline="#000000", fill="#66391E")
        self.legend.create_text(55, 210, anchor="w", font=("Helvetica", 10), text="Building")
        # Pokemon Center
        self.legend.create_rectangle(15, 240, 45, 270, width=1, outline="#000000", fill="#FF0000")
        self.legend.create_text(55, 255, anchor="w", font=("Helvetica", 10), text="Pokemon Center")
        # Pokemart
        self.legend.create_rectangle(15, 285, 45, 315, width=1, outline="#000000", fill="#0000FF")
        self.legend.create_text(55, 300, anchor="w", font=("Helvetica", 10), text="Pokemart")
        # Gym
        self.legend.create_rectangle(15, 330, 45, 360, width=1, outline="#000000", fill="#1E6660")
        self.legend.create_text(55, 345, anchor="w", font=("Helvetica", 10), text="Gym")

        self.df_label = tk.Label(self.window, text="Detection Screen", font=("Helvetica", 12))
        self.df_label.grid(row=0, column=0, columnspan=2, padx=5, pady=5)
        self.detect_frame = tk.Label(self.window, width=720, height=720)
        self.detect_frame.grid(row=1, column=0, rowspan=6, columnspan=2, padx=5, pady=5)

        self.mf_label = tk.Label(self.window, text="Explored Map", font=("Helvetica", 12))
        self.mf_label.grid(row=0, column=2, columnspan=2, padx=5, pady=5)
        self.map_frame = tk.Label(self.window, width=720, height=720)
        self.map_frame.grid(row=1, column=2, rowspan=6, columnspan=2, padx=5, pady=5)

        self.is_paused = True
        self.initial = True
        self.pause_button_text = tk.StringVar()
        self.pause_button_text.set("Start")
        self.pause_button = tk.Button(self.window, textvariable=self.pause_button_text, font=("Helvetica", 12), \
            command=self.pause_ai)
        self.pause_button.grid(row=4, column=4, padx=5, pady=5, sticky="nw")

        self.save_map_button = tk.Button(self.window, text="Save Map", font=("Helvetica", 12), command=self.save_map)
        self.save_map_button.grid(row=5, column=4, padx=5, pady=5, sticky="nw")

        dqnn_train_status = tk.IntVar()
        self.dqnn_train_checkbox = tk.Checkbutton(self.window, text="Train DQNN", variable=dqnn_train_status, \
            font=("Helvetica", 12))
        self.dqnn_train_checkbox.grid(row=6, column=4, padx=5, pady=5, sticky="nw")
        #self.pa.bat_ai.continue_training = self.dqnn_train_checkbox
        

        self.update()
        self.window.mainloop()
    
    def update(self):
        if not (self.is_paused == True and self.initial == False):
            #frame, map_grid = self.pa.run_step()
            ret, frame = self.video.read()
            map_grid = frame.copy()

            frame = cv2.resize(frame, (720,720), interpolation=cv2.INTER_LINEAR)
            frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGBA)
            frame = Image.fromarray(frame)
            frame = ImageTk.PhotoImage(image=frame)
            self.detect_frame.imgtk = frame
            self.detect_frame.configure(image=frame)
            
            # Padding map to make it square
            width = map_grid.shape[1]
            height = map_grid.shape[0]
            
            map_grid = map_grid[:,:,:3]
            padding = 0
            if height < width:
                padding = int((width - height) / 2)
                map_grid = cv2.copyMakeBorder(map_grid, padding, padding, 0, 0, cv2.BORDER_CONSTANT, (0, 0, 0))
            elif height > width:
                padding = int((height - width) / 2)
                map_grid = cv2.copyMakeBorder(map_grid, 0, 0, padding, padding, cv2.BORDER_CONSTANT, (0, 0, 0))

            map_grid = cv2.resize(map_grid, (720,720), interpolation=cv2.INTER_NEAREST)
            self.cur_map_grid = map_grid.copy()
            map_grid = cv2.cvtColor(map_grid, cv2.COLOR_BGR2RGBA)
            map_grid = Image.fromarray(map_grid)
            map_grid = ImageTk.PhotoImage(image=map_grid)
            self.map_frame.imgtk = map_grid
            self.map_frame.configure(image=map_grid)

        self.initial = False
        self.window.after(1, self.update)
    
    def pause_ai(self):
        self.is_paused = not self.is_paused
        if (self.pause_button_text.get() == "Pause"):
            self.pause_button_text.set("Resume")
        else:
            self.pause_button_text.set("Pause")
    
    def save_map(self):
        temp = cv2.resize(self.cur_map_grid, (1080,1080), interpolation=cv2.INTER_NEAREST)
        cv2.imwrite("saved_maps/" + str(self.map_num) + ".png", temp)
        self.map_num += 1

if __name__ == "__main__":
    gui(tk.Tk(), "poke.AI")