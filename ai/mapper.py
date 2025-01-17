import numpy as np
import math
from path_finder import path_finder

# Think of this object as something akin to SLAM. This will basically simultaenously
# localize the player character and map out its surroundings. This live map will be
# used by the neural network that will control the player character
class live_map:
    def __init__(self, w, h, pad, init_ram_vals):#, pid, xpa, ypa):
        # Variables to initialize
        self.window_width = w
        self.window_height = h
        self.padding = pad # Black bars used to make input square
        
        # Num of tiles in x and y axies (+ 1) - the num of tiles is 1-indexed here btw
        self.grid_x = 16
        self.grid_y = 12

        self.tile_size = int(w / (self.grid_x - 1)) # real-world size of square tiles

        ### Internals used by mapper ###
        # The detected map represented as a 2D array
        self.prev_map_grid = np.full((self.grid_y - 1, self.grid_x - 1, 4), [0, 0, 0, 0], dtype=np.uint8) 
        self.cur_map_grid = np.full((self.grid_y - 1, self.grid_x - 1, 4), [0, 0, 0, 0], dtype=np.uint8)
        
        # Coordinates of top_left game view tile in relation to starting point in global map
        self.map_offset_x = 0 
        self.map_offset_y = 0
        # Coordinates of top_left and bot_right tiles for global map, relative to starting point
        self.map_min_offset_x = 0
        self.map_max_offset_x = 14
        self.map_min_offset_y = 0
        self.map_max_offset_y = 10
        # List of all detected in terms of their global coordinates
        self.object_list = []
        # List of tiles that are actually walls/boundaries
        self.boundary_points = []

        # Setting up ram searcher
        #self.ram_search = ram_searcher()
        self.prev_ram = init_ram_vals#ram_searcher.get_vals() # Storing character's position
        self.cur_ram = None

        # Setting up path finder
        self.pf = path_finder()
        self.move_list = []


    # Not the fastest function, is essentially a O(n^2) solution that fills in
    # the tiles covered by detected objects
    def fill_area(self, area_bound, symbol):
        if (np.array_equal(symbol, [66, 135, 245])): # npc
            self.cur_map_grid[area_bound[3]][area_bound[2]][:3] = [66, 135, 245]
        
        #elif (np.array_equal(symbol, [105, 105, 105])): # boundary
        #    self.cur_map_grid[area_bound[3]][area_bound[2]][:3] = [105, 105, 105]
        
        elif (np.array_equal(symbol, [33, 255, 185])): # exit
            if (not np.array_equal(self.cur_map_grid[area_bound[1]][area_bound[0]][:3], [66, 135, 245])):
                self.cur_map_grid[area_bound[1]][area_bound[0]][:3] = [33, 255, 185]
            if (not np.array_equal(self.cur_map_grid[area_bound[1]][area_bound[2]][:3], [66, 135, 245])):
                self.cur_map_grid[area_bound[1]][area_bound[2]][:3] = [33, 255, 185]
        
        else:
            x = area_bound[0] 
            while (x <= area_bound[2]):
                y = area_bound[1]
                while (y <= area_bound[3]):
                    if (not np.array_equal(self.cur_map_grid[y][x][:3], [66, 135, 245])):
                        self.cur_map_grid[y][x][:3] = symbol
                    y += 1
                x += 1


    # Output of inferencing on each input frame is in terms of the frame's pixel coordinates, for our
    # use case, we have to convert these to in-game tiles
    def convert_points_to_grid(self, key_pressed, bounding_box_list):
        tiles = []
        for label, box in bounding_box_list:
            coords = [0, 0, 0, 0]

            # Object top_left corner
            # x1 
            q = box[0] / self.tile_size
            if abs(box[0] - (self.tile_size * math.floor(q))) < \
            abs(box[0] - (self.tile_size * math.ceil(q))):
                coords[0] = math.floor(q)
            else:
                coords[0] = math.ceil(q)
            # y1
            q = (box[1] - self.padding) / self.tile_size
            if abs((box[1] - self.padding + (self.tile_size/2)) - (self.tile_size * math.floor(q))) < \
            abs((box[1] - self.padding) - (self.tile_size * math.ceil(q))):
                coords[1] = math.floor(q)
            else:
                coords[1] = math.ceil(q)

            # Object bot_right corner
            # x2
            q = box[2] / self.tile_size
            if abs(box[2] - (self.tile_size * math.floor(q))) < \
            abs(box[2] - (self.tile_size * math.ceil(q))):
                coords[2] = math.floor(q) - 1
            else:
                coords[2] = math.ceil(q) - 1
            # y2
            q = (box[3] - self.padding) / self.tile_size
            if abs((box[3] - self.padding + (self.tile_size/2)) - (self.tile_size * math.floor(q))) < \
            abs((box[3] - self.padding) - (self.tile_size * math.ceil(q))):
                coords[3] = math.floor(q) - 1
            else:
                coords[3] = math.ceil(q) - 1

            # Converting tiles in terms of local coordinates to global coordinates of entire map
            coords[0] += (self.map_offset_x - self.map_min_offset_x)
            coords[1] += (self.map_offset_y - self.map_min_offset_y)
            coords[2] += (self.map_offset_x - self.map_min_offset_x)
            coords[3] += (self.map_offset_y - self.map_min_offset_y)

            # Skipping appending converted tile if it is just the main agent detected as a NPC
            if (coords[2] == self.map_offset_x - self.map_min_offset_x + 7) and \
                (coords[3] == self.map_offset_y - self.map_min_offset_y + 5):
                continue

            tiles.append((label, coords))
        
        return tiles
    

    def append_handler(self, key_pressed):
        is_appending = False # Flag for when player character is moving into unmapped regions

        # Conditionals below append to the map if the game view tries to pass an edge
        if (key_pressed == 0):
            # If game view tries to shift above global map edge
            if (self.map_offset_y - 1 < self.map_min_offset_y):
                self.grid_y += 1
                self.map_min_offset_y -= 1
                append_arr = np.full((1, self.grid_x - 1, 4), [0, 0, 0, 0], dtype=np.uint8)
                self.cur_map_grid = np.append(append_arr, self.cur_map_grid, axis=0)
                self.map_offset_y -= 1

                is_appending = True
            else:
                self.map_offset_y -= 1
        
        elif (key_pressed == 1):
            # If game view tries to shift right of global map edge
            if (self.map_offset_x + 1 + 14 > self.map_max_offset_x):
                self.grid_x += 1
                self.map_max_offset_x += 1
                append_arr = np.full((self.grid_y - 1, 1, 4), [0, 0, 0, 0], dtype=np.uint8)
                self.cur_map_grid = np.append(self.cur_map_grid, append_arr, axis=1)
                self.map_offset_x += 1

                is_appending = True
            else:
                self.map_offset_x += 1
            
        elif (key_pressed == 2):
            # If game view tries to shift below global map edge
            if (self.map_offset_y + 1 + 10 > self.map_max_offset_y):
                self.grid_y += 1
                self.map_max_offset_y += 1
                append_arr = np.full((1, self.grid_x - 1, 4), [0, 0, 0, 0], dtype=np.uint8)
                self.cur_map_grid = np.append(self.cur_map_grid, append_arr, axis=0)
                self.map_offset_y += 1

                is_appending = True
            else:
                self.map_offset_y += 1
            
        elif (key_pressed == 3):
            # If game view tries to shift to left of global map edge
            if (self.map_offset_x - 1 < self.map_min_offset_x):
                self.grid_x += 1
                self.map_min_offset_x -= 1
                append_arr = np.full((self.grid_y - 1, 1, 4), [0, 0, 0, 0], dtype=np.uint8)
                self.cur_map_grid = np.append(append_arr, self.cur_map_grid, axis=1)
                self.map_offset_x -= 1

                is_appending = True
            else:
                self.map_offset_x -= 1

        # If key_pressed is 'x' or None, do nothing in this case
        else:
            pass

        # Adjusting global coordinates if map is being appended in any of the 4 directions
        # In other words, if player character is stepping into unmapped territory. This is
        # important because all the objects' coordinates will change relative to a map that
        # increases in size
        if (is_appending == True):
            # Yes there is a reason why "right" and "down" are blank
            for label, box in self.object_list:
                if (key_pressed == 0):
                    box[1] += 1
                    box[3] += 1
                elif (key_pressed == 1):
                    pass
                elif (key_pressed == 2):
                    pass
                elif (key_pressed == 3):
                    box[0] += 1
                    box[2] += 1
                else:
                    pass
            
            # Modifying global pos of next frontier as well
            if (key_pressed == 0):
                self.pf.next_frontier[2] += 1
            elif (key_pressed == 3):
                self.pf.next_frontier[1] += 1
            
            # Modifying global pos of unreachable frontiers as well
            temp_set = set()
            for u_frontier in self.pf.unreachable_frontiers:
                if (key_pressed == 0):
                    #self.pf.unreachable_frontiers.remove(u_frontier)
                    x = u_frontier[0]
                    y = u_frontier[1] + 1
                    #u_frontier[1] += 1
                    temp_set.add((x, y))
                elif (key_pressed == 3):
                    #u_frontier[0] += 1
                    #self.pf.unreachable_frontiers.remove(u_frontier)
                    x = u_frontier[0] + 1
                    y = u_frontier[1]
                    temp_set.add((x, y))
            self.pf.unreachable_frontiers = temp_set


    # This function handles detection of new objects and uses this new information to further built
    # the global map
    def add_to_object_list(self, key_pressed, bounding_box_list):
        # Reset map_colour to blank so we can draw our objects after their global coordinates have been changed.
        # This does not alter the visited/unvisited labels as we need this for our frontier detection.
        self.cur_map_grid[:,:,:3] = [0, 0, 0]

        # Function to handle changes in global coordinates if map_grid needs to be appended to
        self.append_handler(key_pressed)

        # Get newly detected objects in terms of tiles
        tiles = self.convert_points_to_grid(key_pressed, bounding_box_list)

        # O(n^2) solution for keeping track of new and old objects. Perhaps a faster method exists?
        # This basically gets the latest detected objects and checks whether they are in fact the same
        # as previously detected objects or are completely new objects
        temp_object_list = [] # Temp list to store newly detected objects
        for new_label, new_box in tiles: # Iterating through objects detected this frame
            is_found = False

            for label, box in self.object_list: # Iterating through previously detected objects
                # This conditional checks whether a new object is the same as an old object by checking if the top_left or
                # bot_right points reside inside an old object's area
 
                if (new_box[0] >= box[0] and new_box[0] <= box[2] and new_box[1] >= box[1] and new_box[1] <= box[3]) or \
                    (new_box[2] >= box[0] and new_box[2] <= box[2] and new_box[3] >= box[1] and new_box[3] <= box[3]):
                    # If this is true then the two objects are indeed the same, now we need to decide whether we keep
                    # the old object or the new one. This is based on the area (size) of the object. We keep the one
                    # with the larger area.
                    new_area = (new_box[2] - new_box[0]) * (new_box[3] - new_box[1])
                    og_area = (box[2] - box[0]) * (box[3] - box[1])
                    if (new_area > og_area):
                        box[:] = new_box[:]
                    # Else we keep the original object as it is

                    # The so-called newly detected object is in-fact an old object, we can safely break from this loop
                    is_found = True
                    break

            # If object is not found, i.e., it is a new object, prepare it for adding to the main object_list
            if (is_found == False):
                temp_object_list.append((new_label, new_box))
        
        # Add newly found objects to list
        self.object_list.extend(temp_object_list)


    def draw_frontiers(self, top_x, top_y):        
        self.local_top_x = top_x
        self.local_top_y = top_y
        self.local_bot_x = top_x + 14
        self.local_bot_y = top_y + 10
        
        for i in range(0, len(self.cur_map_grid)):
            for j in range(0, len(self.cur_map_grid[i])):
                if (j > self.local_top_x and j < self.local_bot_x) and \
                    (i > self.local_top_y and i < self.local_bot_y):
                    self.cur_map_grid[i][j][3] = 1
                    if (np.array_equal(self.cur_map_grid[i][j][:3], [0, 0, 0])):
                        self.cur_map_grid[i][j] = [255, 255, 255, 1]
                elif (self.cur_map_grid[i][j][3] == 1):
                    if (np.array_equal(self.cur_map_grid[i][j][:3], [0, 0, 0])):
                        self.cur_map_grid[i][j][:3] = [255, 255, 255]


    # This is called from main.py to draw our global map. Inputs are the bounding boxes raw data from
    # the frame inferencing and the most recent key pressed by the controller
    def draw_map(self, key_pressed, bounding_box_list, ram_values):
        #self.cur_ram = self.ram_search.get_vals() # Player position from ram searcher
        self.cur_ram = ram_values
        has_collision_occured = False
        
        # Control continues to check for any battle starting. Depending on whether battle starts on
        # end or start of movement, the map will be updated by the conditional above.
        # Wild pokemon battle or trainer battle detected
        if (self.cur_ram[4] == 1) or (self.cur_ram[3] == 1 or self.cur_ram[3] == 2):
            if (self.prev_ram[0] != self.cur_ram[0] or self.prev_ram[1] != self.cur_ram[1]):
                pass
                #return self.cur_map_grid, "battle_collision_post"
                # Need to update map with latest position before 
            else:
                return self.cur_map_grid, "battle_collision_pre"
        
        
        elif self.cur_ram[5] == 1:
            has_collision_occured = True
            self.boundary_points = []
            # Collision has occurred
            if (key_pressed == 0):
                if (np.array_equal(self.prev_map_grid[(self.map_offset_y - self.map_min_offset_y) + 4][(self.map_offset_x - self.map_min_offset_x) + 7][:3], [255, 255, 255])):
                    self.boundary_points.append(((self.map_offset_x - self.map_min_offset_x) + 7, (self.map_offset_y - self.map_min_offset_y) + 4))
            elif (key_pressed == 1):
                if (np.array_equal(self.prev_map_grid[(self.map_offset_y - self.map_min_offset_y) + 5][(self.map_offset_x - self.map_min_offset_x) + 8][:3], [255, 255, 255])):
                    self.boundary_points.append(((self.map_offset_x - self.map_min_offset_x) + 8, (self.map_offset_y - self.map_min_offset_y) + 5))
            elif (key_pressed == 2):
                if (np.array_equal(self.prev_map_grid[(self.map_offset_y - self.map_min_offset_y) + 6][(self.map_offset_x - self.map_min_offset_x) + 7][:3], [255, 255, 255])):
                    self.boundary_points.append(((self.map_offset_x - self.map_min_offset_x) + 7, (self.map_offset_y - self.map_min_offset_y) + 6))
            elif (key_pressed == 3):
                if (np.array_equal(self.prev_map_grid[(self.map_offset_y - self.map_min_offset_y) + 5][(self.map_offset_x - self.map_min_offset_x) + 6][:3], [255, 255, 255])):
                    self.boundary_points.append(((self.map_offset_x - self.map_min_offset_x) + 6, (self.map_offset_y - self.map_min_offset_y) + 5))
            else:
                pass

        # Collision has been successfully detected
        if (has_collision_occured == True):
            for point in self.boundary_points:
                coords = [point[0], point[1], point[0], point[1]]
                if not ((6, coords) in self.object_list):
                    self.object_list.append((6, coords))
                self.fill_area(coords, [105, 105, 105])

            # Used for anything that needs to compare previous map state with new map state
            self.prev_map_grid = self.cur_map_grid
            self.prev_ram = self.cur_ram
            
            # Draw frontiers on map
            self.draw_frontiers((self.map_offset_x - self.map_min_offset_x), \
                (self.map_offset_y - self.map_min_offset_y))
            
            return self.cur_map_grid, "normal_collision"
        
        else:
            # We will increase the consecutive normal movmenets by 1 since at this point no collision has occured
            self.pf.consecutive_movements += 1
            if (self.pf.consecutive_movements >= 2):
                # We only reset the consecutive collisions once we have achieved two consecutive movements.
                self.pf.consecutive_collisions = 0

            # Use bounding box list to add to our list of global objects
            self.add_to_object_list(key_pressed, bounding_box_list)

            # This block handles drawing of tiles in the map with different colours on the grayscale spectrum
            symbol = None
            for label, box in self.object_list:
                if (label == 0): # pokecen
                    symbol = [0, 0, 255] # red
                elif (label == 1): # pokemart
                    symbol = [255, 0, 0] # blue
                elif (label == 2): # npc
                    symbol = [66, 135, 245] # orange
                elif (label == 3): # house
                    symbol = [30, 57, 102] # brown
                elif (label == 4): # gym
                    symbol = [96, 102, 30] # turqoise
                elif (label == 5): # exit
                    symbol = [33, 255, 185] # yellow
                elif (label == 6): # wall/boundary
                    symbol = [105, 105, 105] # grey
                #elif (label == 7): # grass
                #    symbol = [33, 166, 28] # green

                self.fill_area(box, symbol)
            # Draw player character position for localization purpose # green
            self.cur_map_grid[(self.map_offset_y - self.map_min_offset_y) + 5]\
                [(self.map_offset_x - self.map_min_offset_x) + 7][:3] = [149, 255, 0]

            # Draw frontiers on map
            self.draw_frontiers((self.map_offset_x - self.map_min_offset_x), \
                (self.map_offset_y - self.map_min_offset_y))

            # Used for anything that needs to compare previous map state with new map state
            self.prev_map_grid = self.cur_map_grid
            self.prev_ram = self.cur_ram

        # Control continues to check for any battle starting. Depending on whether battle starts on
        # end or start of movement, the map will be updated by the conditional above.
        # Wild pokemon battle or trainer battle detected
        if (self.cur_ram[4] == 1) or (self.cur_ram[3] == 1 or self.cur_ram[3] == 2):
            if (key_pressed != None): # If battle starts after movement has been performed
                return self.cur_map_grid, "battle_collision_post"
            else:
                return self.cur_map_grid, "battle_collision_pre"
        
        return self.cur_map_grid, "no_collision"

    def get_movelist(self):
        # Get best frontier to move towards
        self.move_list = self.pf.get_next_frontier((self.map_offset_x - self.map_min_offset_x), \
            (self.map_offset_y - self.map_min_offset_y), \
            self.cur_map_grid)
        
        return self.move_list

    def move_list_to_target(self, target_type, mode="closest"):
        pass